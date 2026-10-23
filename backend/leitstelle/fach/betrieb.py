"""Betrieb: der echte Vollzug für den Entscheidungskern.

Hält den Verbund (Laufzustand), gleicht ihn im Takt mit den Diensten ab, führt aus, was der Kern
beschließt (laden, entladen, umleiten, Hintergrund), gibt wartende Aufrufe frei und misst jede Lade-
und Laufzeit. Alle Änderungen am Verbund geschehen in der Ereignisschleife zwischen zwei `await`, der
Kern selbst ist synchron; so gibt es keine halben Zustände.

Dasselbe tut im Test die Schein-Welt (`simulation/welt.py`); beide erfüllen `kern.umschichter.Vollzug`.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel

from ..kern.leitstelle import Leitstelle
from ..kern.messungen import Messwerk
from ..kern.modelle import Anwendung, Auftrag, Dienst, Knoten, Massnahme, Modell, Verbund
from ..kern.werte import WORT, Auftragszustand, Betriebsmodus, Dienstzustand, Faehigkeit, Massnahmenzustand, Modellzustand, Prioritaet, Zone
from ..konfig import Konfig
from ..ports.ablage.eintraege import (Adapterart, AnwendungEintrag, AuftragEintrag, Ausgang, BetriebEinstellung, Bewegung, DienstEintrag, KnotenEintrag,
                                      PruefEintrag, Richtung, Schlafstand, Schritt, SteckbriefEintrag)
from ..ports.agenten import AgentVerbindung, Agentenvermittlung
from ..ports.ablage.repositorien import Ablage
from ..ports.dienste import AdapterFabrik, DienstAdapter, DienstFehler, ModellBericht, agent_adresse
from ..ports.tresor import Tresor, fingerabdruck
from ..ports.uhr import Uhr
from ..protokoll.knoten import KnotenSchlaeft, Selbstauskunft
from ..protokoll.steckbrief import Messwerte, Steckbrief
from ..protokoll.umschlag import umschlag
from .ereignisse import Ereignisbus
from .fehler import Ablehnung, Zusatz
from .schreibfolge import Schreibfolge
from .steckbrief import messwerte_aus, zusammensetzen
from ..kern.text import komma, schlaf_satz

log = logging.getLogger("leitstelle.betrieb")

LADEPAUSEN_S = (10.0, 20.0, 40.0, 60.0)    # Pausen nach abgelehnten Ladeversuchen, wachsend
LADEFEHLER_BIS_ABBRUCH = 3                  # so oft darf das Laden für einen Auftrag scheitern
ABRISSE_BIS_STOERUNG = 3                    # so viele abgerissene Anfragen in Folge, bis ein Dienst als gestört gilt


def _schlafdauer(s: float) -> str:
    """Wie lange ein Rechner schlief, für die Meldung beim Aufwachen."""
    return f"{komma(s / 3600)} h" if s >= 3600 else f"{max(1, round(s / 60))} min"


def modell_kennung(dienst: str, schluessel: str) -> str:
    """Stabil über Neustarts und Abgleiche: dasselbe Modell auf demselben Dienst hat dieselbe Kennung."""
    return uuid5(NAMESPACE_URL, f"leitstelle:{dienst}:{schluessel}").hex


@dataclass
class ModellOrt:
    """Wie die Leitstelle ein Modell beim Dienst anspricht."""

    schluessel: str
    instanzen: list[str] = field(default_factory=list)
    kontext: int | None = None
    weitere: tuple[str, int] | None = None   # weitere Instanz, noch nicht geladen: Schlüssel der Grundinstanz und Stufe

    @property
    def anfragename(self) -> str:
        return self.instanzen[0] if self.instanzen else self.schluessel


@dataclass
class Pruefstand:
    """Wann ein abgefragter Dienst wieder gefragt wird: gesund nach seinem Abgleichabstand, nach Fehlschlägen in
    wachsenden Abständen (ZUSAMMENSPIEL Z4)."""

    fehlschlaege: int = 0
    naechste_s: float = 0.0
    seit_s: float | None = None        # erster Fehlschlag der laufenden Reihe


@dataclass
class Messung:
    erstes_stueck_s: float | None = None
    token_ein: int | None = None
    token_aus: int | None = None
    teilergebnis_zeichen: int = 0


class Freigabe(BaseModel):
    """Eine Zeile der Vorschau "Speicher freigeben"."""

    modell: str
    name: str
    gb: float
    darf: bool
    grund: str


class Lauf:
    """Verbindung zwischen einem wartenden Aufruf und seinem Auftrag im Verbund."""

    def __init__(self, kennung: str, titel: str) -> None:
        self.kennung = kennung
        self.titel = titel
        self.freigabe = asyncio.Event()     # Modell bereit, Platz frei: los
        self.ende = asyncio.Event()         # abgelehnt oder abgebrochen
        self.grund: str | None = None
        self.begruendung: str = ""
        self.zusatz: Zusatz | None = None   # geht als error.x-leitstelle an die Anwendung (etwa schlafende Rechner)
        self.danach_sperren: str | None = None   # Auslaufen: nach dem Ende die Anwendung sperren, mit diesem Grund
        self.ladefehler = 0
        self.schritte: list[Schritt] = []
        self._stand: tuple[str, str] | None = None
        self.abbrecher: Callable[[], None] | None = None   # setzt die Durchleitung: schließt den Strom des Dienstes

    def notieren(self, zeit_s: float, zustand: Auftragszustand, text: str) -> None:
        """Hält einen Schritt fest, wenn sich Zustand oder Begründung geändert haben."""
        if self._stand != (zustand.value, text):
            self._stand = (zustand.value, text)
            self.schritte.append(Schritt(zeit_s=zeit_s, zustand=zustand, text=text))

    def beenden_mit(self, grund: str, begruendung: str, zusatz: Zusatz | None = None) -> None:
        if not self.ende.is_set():
            self.grund, self.begruendung, self.zusatz = grund, begruendung, zusatz
            self.ende.set()
            if self.abbrecher:
                self.abbrecher()


class Betrieb:
    def __init__(self, ablage: Ablage, tresor: Tresor, uhr: Uhr, fabrik: AdapterFabrik, bus: Ereignisbus, konfig: Konfig,
                 agenten: Agentenvermittlung | None = None) -> None:
        self.ablage, self.tresor, self.uhr, self.fabrik, self.bus, self.konfig = ablage, tresor, uhr, fabrik, bus, konfig
        self.agenten = agenten or Agentenvermittlung()   # dieselbe Vermittlung wie in der Adapter-Fabrik
        self.verbund = Verbund()
        self.messwerk = Messwerk()
        self.kern = Leitstelle()
        self.adapter: dict[str, DienstAdapter] = {}
        self.dienste: dict[str, DienstEintrag] = {}
        self.knoten: dict[str, KnotenEintrag] = {}
        self.anwendungen: dict[str, AnwendungEintrag] = {}
        self.aliasse: dict[str, str] = {}
        self.steuerbar: dict[str, bool] = {}
        self.dienst_meldung: dict[str, str] = {}
        self.pruefstand: dict[str, Pruefstand] = {}
        self.abrisse: dict[str, int] = {}                         # je Dienst: abgerissene Anfragen in Folge
        self.auskunft: dict[str, Selbstauskunft] = {}            # je Modell: was der Dienst über es sagt
        self.steckbriefe_hand: dict[str, SteckbriefEintrag] = {}  # je Familie: von Hand eingetragen
        self.gemessen: dict[str, Messwerte] = {}                  # je Familie: aus dem Verlauf
        self._letzte_messung = 0.0
        self.orte: dict[str, ModellOrt] = {}
        self.laeufe: dict[str, Lauf] = {}
        self.ladeversuche: dict[str, int] = {}
        self.ladeaufgaben: dict[str, asyncio.Task] = {}
        self.entladungen: dict[str, set[asyncio.Task]] = {}   # je Knoten laufendes Entladen; Laden dort wartet darauf
        self.massnahmen: deque[Massnahme] = deque(maxlen=40)
        self.meldungen: deque[tuple[float, str]] = deque(maxlen=60)
        self._gesperrt_gemeldet: dict[tuple, float] = {}
        self._hintergrund: set[asyncio.Task] = set()
        self.schreibfolge = Schreibfolge()   # alles, was im Hintergrund in die Ablage geht, in der Reihenfolge des Geschehens
        self._schleife: asyncio.Task | None = None
        self._letzter_abgleich = 0.0
        self._letzte_umschichtung = 0.0
        self.aenderung = 0                  # zählt Änderungen; das Lagebild wird nur bei Änderung neu gesendet

    # ── Start und Ende ───────────────────────────────────────────────────
    async def starten(self, mit_schleife: bool = True) -> None:
        jetzt = self.uhr.jetzt()
        self.verbund.regelwerk = await self.ablage.einstellungen.regelwerk()
        einst = await self.ablage.einstellungen.betrieb()
        self.verbund.betriebsmodus, self.verbund.hintergrund_erlaubt = einst.modus, einst.hintergrund_an
        self.messwerk = await self.ablage.messungen.laden()
        abgebrochen = await self.ablage.auftraege.offene_als_abgebrochen(jetzt)
        if abgebrochen:
            self.melden(f"{abgebrochen} offene Aufträge aus der Zeit vor dem Neustart als abgebrochen vermerkt")
        for k in await self.ablage.knoten.alle():
            self.knoten_setzen(k)
        await self._schlaf_wiederherstellen()
        for d in await self.ablage.dienste.alle():
            self.dienst_setzen(d)
        for a in await self.ablage.anwendungen.alle():
            self.anwendung_setzen(a)
        self.aliasse = {a.alias: a.familie for a in await self.ablage.aliasse.alle()}
        self.steckbriefe_hand = {e.familie: e for e in await self.ablage.steckbriefe.alle()}
        await self.abgleichen()
        await self._messwerte_holen()
        if mit_schleife:
            self._schleife = asyncio.create_task(self._takt_schleife(), name="leitstelle-takt")

    async def beenden(self) -> None:
        if self._schleife:
            self._schleife.cancel()
            try:
                await self._schleife
            except asyncio.CancelledError:
                pass
        for lauf in self.laeufe.values():
            lauf.beenden_mit("wartung", "Die Leitstelle wird beendet.")
        for t in list(self.ladeaufgaben.values()) + list(self._hintergrund):
            t.cancel()
        await asyncio.gather(*self._hintergrund, *self.ladeaufgaben.values(), return_exceptions=True)
        await self.schreibfolge.leeren()
        await self.ablage.messungen.speichern(self.messwerk)
        for a in self.adapter.values():
            await a.schliessen()

    def _nebenbei(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Was den Ablauf nicht aufhalten soll (schließen, abgleichen, entladen); Fehler landen im Protokoll. Schreiben in
        die Ablage geht über die Schreibfolge, damit nichts Älteres etwas Neueres überholt."""
        t = asyncio.create_task(coro)
        self._hintergrund.add(t)

        def fertig(x: asyncio.Task) -> None:
            self._hintergrund.discard(x)
            if not x.cancelled() and x.exception():
                log.error("Hintergrundaufgabe gescheitert: %r", x.exception())

        t.add_done_callback(fertig)
        return t

    def geaendert(self) -> None:
        self.aenderung += 1

    # ── Verzeichnis in den Verbund übernehmen ────────────────────────────
    def knoten_setzen(self, k: KnotenEintrag) -> None:
        self.knoten[k.kennung] = k
        alt = self.verbund.knoten.get(k.kennung)
        fenster = (k.hintergrund_von, k.hintergrund_bis) if k.hintergrund_von is not None and k.hintergrund_bis is not None else None
        self.verbund.knoten[k.kennung] = Knoten(kennung=k.kennung, name=k.name, zone=k.zone, speicher_gb=k.speicher_gb, system_gb=k.system_gb,
                                                 erreichbar=alt.erreichbar if alt else True, schlaeft_seit_s=alt.schlaeft_seit_s if alt else None,
                                                 hintergrund_fenster=fenster, budget_fest_gb=k.budget_fest_gb)
        v = self.agenten.verbindung(k.kennung)
        if v and v.messwerte:
            self.messwerte_uebernehmen(v)
        self.geaendert()

    def knoten_entfernen(self, kennung: str) -> None:
        self.knoten.pop(kennung, None)
        self.verbund.knoten.pop(kennung, None)
        self.geaendert()

    def dienst_setzen(self, d: DienstEintrag) -> None:
        alt_adapter = self.adapter.pop(d.kennung, None)
        if alt_adapter:
            self._nebenbei(alt_adapter.schliessen())
        self.dienste[d.kennung] = d
        zugang = self.tresor.entschluesseln(d.zugang_geheim) if d.zugang_geheim else None
        self.adapter[d.kennung] = self.fabrik(d.art, d.adresse, zugang, lambda k=d.kennung: self.verbund.anfrage_gesendet(k, self.uhr.jetzt()))
        self.pruefstand.pop(d.kennung, None)            # geändert: sofort neu prüfen
        alt = self.verbund.dienste.get(d.kennung)
        self.verbund.dienste[d.kennung] = Dienst(kennung=d.kennung, name=d.name, knoten=d.knoten, art=d.art.value,
                                                  faehigkeiten=alt.faehigkeiten if alt else set(), zustand=alt.zustand if alt else Dienstzustand.NICHT_ERREICHBAR,
                                                  installiert=False, extern=d.extern, plaetze=d.plaetze, anfragen_je_minute=d.anfragen_je_minute,
                                                  anfragen_s=alt.anfragen_s if alt else [], gesperrt_bis_s=alt.gesperrt_bis_s if alt else None,
                                                  einbettung_instanzen=d.einbettung_instanzen, einbettung_spielraum_gb=d.einbettung_spielraum_gb)
        self.geaendert()

    def dienst_entfernen(self, kennung: str) -> None:
        a = self.adapter.pop(kennung, None)
        if a:
            self._nebenbei(a.schliessen())
        self.dienste.pop(kennung, None)
        self.verbund.dienste.pop(kennung, None)
        for mk in [m.kennung for m in self.verbund.modelle.values() if m.dienst == kennung]:
            self.verbund.modelle.pop(mk, None)
            self.orte.pop(mk, None)
            self.auskunft.pop(mk, None)
        self.geaendert()

    def anwendung_setzen(self, a: AnwendungEintrag) -> None:
        self.anwendungen[a.kennung] = a
        self.verbund.anwendungen[a.kennung] = Anwendung(kennung=a.kennung, name=a.name, prioritaet=a.prioritaet, faehigkeiten=set(a.faehigkeiten),
                                                         zonen=set(a.zonen), extern_erlaubt=a.extern_erlaubt, ketten=dict(a.ketten), gleichzeitig=a.gleichzeitig)
        self.geaendert()

    def anwendung_entfernen(self, kennung: str) -> None:
        self.anwendungen.pop(kennung, None)
        self.verbund.anwendungen.pop(kennung, None)
        self.geaendert()

    def anwendung_zum_schluessel(self, schluessel: str) -> AnwendungEintrag | None:
        fp = fingerabdruck(schluessel)
        return next((a for a in self.anwendungen.values() if a.schluessel_fingerabdruck == fp), None)

    # ── Knoten-Agenten ───────────────────────────────────────────────────
    def knoten_zum_agentschluessel(self, schluessel: str) -> KnotenEintrag | None:
        fp = fingerabdruck(schluessel)
        return next((k for k in self.knoten.values() if k.agent_fingerabdruck == fp), None)

    def agentdienst(self, knoten: str) -> str | None:
        """Kennung des Dienstes, unter dem die Prozessdienste dieses Knotens erscheinen."""
        return next((d.kennung for d in self.dienste.values() if d.art == Adapterart.AGENT and d.knoten == knoten), None)

    def agent_angemeldet(self, v: AgentVerbindung) -> None:
        """Die Anmeldung des Maschinenraums hebt einen Schlaf auf: der Rechner ist wach."""
        k = self.knoten[v.knoten]
        self.melden(f"Maschinenraum auf {k.name} verbunden ({v.anmeldung.betriebssystem}, Fassung {v.anmeldung.agent_version})")
        self.bus.senden(umschlag("knoten.angemeldet", {"knoten": k.kennung, "name": k.name, **v.anmeldung.model_dump(mode="json")}))
        kn = self.verbund.knoten.get(v.knoten)
        if kn is not None and kn.schlaeft_seit_s is not None:
            self._wecken(kn, f"{kn.name} ist aufgewacht nach {_schlafdauer(self.uhr.jetzt() - kn.schlaeft_seit_s)}")
        self.geaendert()

    def agent_getrennt(self, knoten: str) -> None:
        """Ohne Agent gelten wieder die eingetragenen Werte des Rechners."""
        e = self.knoten.get(knoten)
        k = self.verbund.knoten.get(knoten)
        if e is None or k is None:
            return
        k.system_gb, k.speicher_gb = e.system_gb, e.speicher_gb
        if k.schlaeft:
            self.melden(f"Maschinenraum auf {e.name} getrennt: der Rechner schläft")
        else:
            self.melden(f"Maschinenraum auf {e.name} getrennt; es gelten wieder die eingetragenen Speicherwerte")
        self.bus.senden(umschlag("knoten.getrennt", {"knoten": knoten, "name": e.name}))
        dienst = self.agentdienst(knoten)
        if dienst:
            self._nebenbei(self._abgleich(dienst))   # seine Dienste sofort als nicht erreichbar zeigen (schläft er: als schlafend)
        self.geaendert()

    # ── Schlaf der Rechner ───────────────────────────────────────────────
    def agent_schlaeft(self, v: AgentVerbindung, meldung: KnotenSchlaeft) -> None:
        """Der Rechner schläft gleich ein (`knoten.schlaeft`): kein Ausfall, sondern Warten, bis er wach ist. Laufende
        Aufträge auf ihm enden mit `rechner_schlaeft` (auch ohne Automatik, sie hingen sonst), zugeteilte und wartende
        entscheidet der Zuteiler neu; seine Dienste werden bis zum Aufwachen nicht geprüft und zählen keine Fehlschläge."""
        k = self.verbund.knoten.get(v.knoten)
        if k is None:
            return
        self._zeit_setzen()
        if k.schlaeft_seit_s is None:
            k.schlaeft_seit_s = self.verbund.zeit_s
        k.erreichbar = False
        for d in self.verbund.dienste_auf(k.kennung):
            d.zustand = Dienstzustand.SCHLAEFT
            self.pruefstand.pop(d.kennung, None)
        self.schreibfolge.einreihen(self.ablage.einstellungen.schlaf_speichern(self._schlafstand()))
        self._laufende_beenden(k.kennung, "rechner_schlaeft", schlaf_satz([k.name]), Zusatz(rechner=[k.name]))
        self.wartende_neu_einreihen(k.kennung)
        self.melden(f"{k.name} schläft ({WORT[meldung.grund.value]}); Aufträge warten in den Apps, bis er wach ist")
        self.bus.senden(umschlag("knoten.schlaeft", {"knoten": k.kennung, "name": k.name, "grund": meldung.grund.value}))
        self.anstossen()

    async def schlaf_beenden(self, knoten: str, wer: str) -> None:
        """"Nicht mehr warten": der Rechner gilt wieder als wach, aber nicht erreichbar, bis seine Dienste antworten.
        Für einen Rechner, der aufgewacht ist, ohne dass sich sein Maschinenraum meldet (oder der nie aufwacht)."""
        k = self.verbund.knoten.get(knoten)
        if k is None:
            raise Ablehnung("unbekannt", "Diesen Rechner gibt es nicht.")
        if k.schlaeft_seit_s is None:
            raise Ablehnung("unbekannt", f"{k.name} schläft nicht.")
        self._wecken(k, f"{k.name}: Schlafzustand von Hand beendet; seine Dienste werden wieder geprüft")
        await self.ablage.pruefung.anhaengen(PruefEintrag(zeit_s=self.uhr.jetzt(), wer=wer, was="Schlafzustand von Hand beendet", gegenstand=k.name))

    def _wecken(self, k: Knoten, text: str) -> None:
        """Ende des Schlafs: die Dienste des Rechners gelten als ungeprüft und werden sofort gefragt (nicht erst nach den
        wachsenden Abständen eines Ausfalls)."""
        k.schlaeft_seit_s = None
        for d in self.verbund.dienste_auf(k.kennung):
            d.zustand = Dienstzustand.NICHT_ERREICHBAR
            self.pruefstand.pop(d.kennung, None)
        self.schreibfolge.einreihen(self.ablage.einstellungen.schlaf_speichern(self._schlafstand()))
        self.melden(text)
        self.bus.senden(umschlag("knoten.aufgewacht", {"knoten": k.kennung, "name": k.name}))
        self._nebenbei(self._knoten_pruefen(k.kennung))
        self.geaendert()

    async def _knoten_pruefen(self, knoten: str) -> None:
        """Alle abgefragten Dienste eines Rechners sofort prüfen; der Maschinenraum meldet seine selbst."""
        await asyncio.gather(*(self._abgleich(d.kennung) for d in self.verbund.dienste_auf(knoten)
                               if d.kennung in self.adapter and not self.adapter[d.kennung].meldet_sich_selbst))
        self._erreichbarkeit_setzen()
        self.anstossen()

    def _schlafstand(self) -> Schlafstand:
        return Schlafstand(seit_s={k.kennung: k.schlaeft_seit_s for k in self.verbund.knoten.values() if k.schlaeft_seit_s is not None})

    async def _schlaf_wiederherstellen(self) -> None:
        """Nach dem Neustart der Leitstelle: wer schlief, schläft weiter, bis sich sein Maschinenraum meldet."""
        for kennung, seit in (await self.ablage.einstellungen.schlaf()).seit_s.items():
            k = self.verbund.knoten.get(kennung)
            if k is not None:
                k.schlaeft_seit_s, k.erreichbar = seit, False
                self.melden(f"{k.name} schläft noch (seit dem Neustart der Leitstelle vermerkt)")

    def messwerte_uebernehmen(self, v: AgentVerbindung) -> None:
        """Gemessener Speicher ersetzt die Schätzung: was die bekannten Modelle nicht wirklich belegen, belegt das System.
        Verplant wird für die Modelle trotzdem ihr Bedarf; so bleibt Platz für Dienste, die noch wachsen."""
        k = self.verbund.knoten.get(v.knoten)
        if k is None or v.messwerte is None:
            return
        k.speicher_gb = round(v.messwerte.speicher_gesamt_gb, 2)
        k.system_gb = round(max(0.0, v.messwerte.speicher_belegt_gb - self.verbund.belegt_bekannt_gb(v.knoten)), 2)
        self.geaendert()

    async def agent_dienste(self, v: AgentVerbindung) -> None:
        """Neue Dienstliste des Agenten: beim ersten Mal den Dienst `agent` anlegen, dann sofort abgleichen."""
        dienst = self.agentdienst(v.knoten)
        if dienst is None and v.dienste.dienste:
            k = self.knoten[v.knoten]
            e = DienstEintrag(kennung=uuid4().hex, name=f"Dienste auf {k.name}", art=Adapterart.AGENT, adresse=agent_adresse(v.knoten),
                              knoten=v.knoten, plaetze=1)
            await self.ablage.dienste.speichern(e)
            self.dienst_setzen(e)
            self.melden(f"{e.name} eingerichtet: {len(v.dienste.dienste)} Dienste im Maschinenraum")
            dienst = e.kennung
        if dienst:
            await self._abgleich(dienst)
            self.geaendert()

    # ── Abgleich mit den Diensten ────────────────────────────────────────
    async def abgleichen(self) -> None:
        """Fragt jeden fälligen Dienst nach Zustand und Modellen (Dienste, die sich selbst melden, jedes Mal)."""
        jetzt = self.uhr.jetzt()
        faellig = [k for k, a in self.adapter.items() if a.meldet_sich_selbst or jetzt >= self.pruefstand.get(k, Pruefstand()).naechste_s]
        await asyncio.gather(*(self._abgleich(k) for k in faellig))
        self._erreichbarkeit_setzen()
        self._letzter_abgleich = self.uhr.jetzt()
        self.geaendert()

    def _erreichbarkeit_setzen(self) -> None:
        """Ein Rechner ist erreichbar, wenn einer seiner Dienste antwortet; ein schlafender bleibt es nicht, bis er wach ist."""
        for k in self.verbund.knoten.values():
            if k.schlaeft:
                continue
            dienste = self.verbund.dienste_auf(k.kennung)
            erreichbar = any(d.zustand not in (Dienstzustand.NICHT_ERREICHBAR, Dienstzustand.AUSFALL) for d in dienste) if dienste else True
            if erreichbar != k.erreichbar:
                k.erreichbar = erreichbar
                self.melden(f"{k.name} ist {'wieder erreichbar' if erreichbar else 'nicht erreichbar'}")

    async def _abgleich(self, dienst: str) -> None:
        adapter = self.adapter.get(dienst)
        if adapter is None:
            return
        if self.verbund.auf_schlafendem(dienst):
            self.verbund.dienste[dienst].zustand = Dienstzustand.SCHLAEFT   # nicht fragen: kein Fehlschlag, kein Ausfall
            return
        bericht = await adapter.zustand()
        d = self.verbund.dienste.get(dienst)
        if d is None or self.verbund.auf_schlafendem(dienst):   # während der Abfrage entfernt oder eingeschlafen
            return
        neu = Dienstzustand.BEREIT if bericht.erreichbar else self._fehlschlag_vermerken(dienst) if not adapter.meldet_sich_selbst else Dienstzustand.NICHT_ERREICHBAR
        if bericht.erreichbar and not adapter.meldet_sich_selbst:
            self._gesund_vermerken(dienst)
        if neu != d.zustand:
            p = self.pruefstand.get(dienst)
            naechste = f"; nächste Prüfung in {komma(p.naechste_s - self.uhr.jetzt())} s" if p and p.fehlschlaege else ""
            self.melden(f"{d.name}: {WORT[neu.value]}{', ' + bericht.meldung if bericht.meldung and not bericht.erreichbar else ''}{naechste}")
        d.zustand = neu
        self.steuerbar[dienst] = bericht.steuerbar
        self.dienst_meldung[dienst] = bericht.meldung
        if not bericht.erreichbar:
            return
        jetzt = self.uhr.jetzt()
        gesehen: set[str] = set()
        for mb in bericht.modelle:
            kennung = self._kennung_fuer(dienst, mb)
            if kennung not in self.verbund.modelle and self._startet_noch(dienst, mb):
                continue                     # gehört zu einer weiteren Instanz, deren Laden gerade zurückkommt
            gesehen.add(kennung)
            self._modell_abgleichen(kennung, d, mb, bericht.steuerbar, jetzt)
        for m in [m for m in self.verbund.modelle.values() if m.dienst == dienst and m.kennung not in gesehen]:
            if not self.verbund.belegung(m.kennung) and m.kennung not in self.ladeaufgaben:   # eine startende Instanz meldet sich gleich
                self.verbund.modelle.pop(m.kennung, None)
                self.orte.pop(m.kennung, None)
                self.auskunft.pop(m.kennung, None)
        d.faehigkeiten = set().union(*(m.faehigkeiten for m in self.verbund.modelle_von(dienst))) if self.verbund.modelle_von(dienst) else set()

    def _kennung_fuer(self, dienst: str, mb: ModellBericht) -> str:
        """Eine weitere Instanz, die die Leitstelle gestartet hat, behält ihre Kennung: geplant wurde sie unter
        `<familie>.<stufe>`, ihre Kennung beim Dienst vergibt der Dienst erst beim Laden (Modell-Läufer: `<schlüssel>:<n>`)."""
        if mb.familie and mb.instanzen:
            for kennung, ort in self.orte.items():
                m = self.verbund.modelle.get(kennung)
                if m is not None and m.dienst == dienst and m.zusatz and ort.instanzen[:1] == mb.instanzen[:1]:
                    return kennung
        return modell_kennung(dienst, mb.schluessel)

    def _startet_noch(self, dienst: str, mb: ModellBericht) -> bool:
        """Meldet der Dienst eine weitere Instanz, während die Leitstelle noch auf die Antwort ihres Ladens wartet?"""
        return mb.familie is not None and any(
            m.dienst == dienst and m.familie == mb.familie and m.zusatz and k in self.ladeaufgaben and not self.ort(k).instanzen
            for k, m in self.verbund.modelle.items())

    def _gesund_vermerken(self, dienst: str) -> None:
        e = self.dienste.get(dienst)
        abstand = e.abgleich_s if e and e.abgleich_s else self.konfig.extern_abgleich_s if e and e.extern else self.konfig.dienst_takt_s
        self.pruefstand[dienst] = Pruefstand(naechste_s=self.uhr.jetzt() + abstand)

    def _fehlschlag_vermerken(self, dienst: str) -> Dienstzustand:
        """Abstand verdoppelt sich je Fehlschlag (bis höchstens einen Tag); ab dem n-ten in Folge heißt es Ausfall."""
        k, jetzt = self.konfig, self.uhr.jetzt()
        alt = self.pruefstand.get(dienst, Pruefstand())
        fehlschlaege = alt.fehlschlaege + 1
        abstand = min(k.pruefung_ab_s * 2 ** (fehlschlaege - 1), k.pruefung_hoechstens_s)
        self.pruefstand[dienst] = Pruefstand(fehlschlaege=fehlschlaege, naechste_s=jetzt + abstand, seit_s=alt.seit_s or jetzt)
        return Dienstzustand.AUSFALL if fehlschlaege >= k.ausfall_ab_fehlschlag else Dienstzustand.NICHT_ERREICHBAR

    async def dienst_pruefen(self, dienst: str, wer: str) -> Dienstzustand:
        """"Jetzt prüfen": sofort fragen, unabhängig vom Prüfplan; antwortet der Dienst, gilt wieder der normale Abstand."""
        if dienst not in self.adapter:
            raise Ablehnung("unbekannt", "Diesen Dienst gibt es nicht.")
        await self._abgleich(dienst)
        self._zeit_setzen()
        self.anstossen()
        await self.ablage.pruefung.anhaengen(PruefEintrag(zeit_s=self.uhr.jetzt(), wer=wer, was="Dienst von Hand geprüft", gegenstand=self.dienste[dienst].name))
        return self.verbund.dienste[dienst].zustand

    def verbindung_abgerissen(self, dienst: str, meldung: str) -> bool:
        """Eine Anfrage erreichte den Dienst nicht oder riss ab. Erst nach `ABRISSE_BIS_STOERUNG` in Folge gilt er als
        gestört (dann bekommt er bis zur nächsten erfolgreichen Prüfung keine Aufträge); liefert, ob es so weit ist."""
        self.abrisse[dienst] = self.abrisse.get(dienst, 0) + 1
        if self.abrisse[dienst] < ABRISSE_BIS_STOERUNG:
            return False
        self.abrisse[dienst] = 0
        self.dienst_gestoert(dienst, meldung)
        return True

    def verbindung_gesund(self, dienst: str) -> None:
        """Der Dienst hat geantwortet: die Reihe der Abrisse ist unterbrochen."""
        self.abrisse.pop(dienst, None)

    def dienst_gestoert(self, dienst: str, meldung: str) -> None:
        """Eine Anfrage erreichte den Dienst nicht: bis zur nächsten erfolgreichen Prüfung bekommt er keine Aufträge."""
        d, a = self.verbund.dienste.get(dienst), self.adapter.get(dienst)
        if d is None or a is None or a.meldet_sich_selbst or self.verbund.auf_schlafendem(dienst):
            return
        d.zustand = self._fehlschlag_vermerken(dienst)
        self.melden(f"{d.name}: {WORT[d.zustand.value]} ({meldung[:120]}); nächste Prüfung in {komma(self.pruefstand[dienst].naechste_s - self.uhr.jetzt())} s")

    def dienst_ueberlastet(self, dienst: str, warte_s: float, status: int) -> None:
        """Der Dienst meldete Überlast (429, extern auch 5xx): gesperrt für seine Wartezeit, kein Fehlschlag."""
        d = self.verbund.dienste.get(dienst)
        if d is None:
            return
        self._zeit_setzen()
        d.gesperrt_bis_s = self.verbund.zeit_s + warte_s
        was = "zu viele Anfragen" if status == 429 else f"Überlast (Antwort {status})"
        self.melden(f"{d.name} meldet {was}; gesperrt für {komma(warte_s)} s")

    # ── Steckbrief (PROTOKOLL 4.8) ───────────────────────────────────────
    async def _messwerte_holen(self) -> None:
        self.gemessen = messwerte_aus(await self.ablage.auftraege.fertige_mit_familie())
        self._letzte_messung = self.uhr.jetzt()

    def steckbrief(self, m: Modell) -> Steckbrief:
        d = self.verbund.dienste[m.dienst]
        zone = Zone.EXTERN if d.extern else (self.verbund.knoten[d.knoten].zone if d.knoten in self.verbund.knoten else Zone.HEIM)
        gemessen = self.gemessen.get(m.familie, Messwerte()).model_copy()
        lade = self.messwerk.ladezeiten.get(f"{m.familie}@{d.knoten}") if d.knoten else None
        if lade and lade.anzahl:
            gemessen.ladezeit_s = round(lade.wert, 1)
        return zusammensetzen(m, self.auskunft.get(m.kennung, Selbstauskunft()), self.steckbriefe_hand.get(m.familie),
                              self.ort(m.kennung).kontext, zone, d.anfragen_je_minute, gemessen)

    async def steckbrief_setzen(self, e: SteckbriefEintrag, wer: str) -> None:
        """Von Hand: ganz leer entfernt den Eintrag, dann gilt wieder nur die Auskunft des Dienstes."""
        if not any(m.familie == e.familie for m in self.verbund.modelle.values()):
            raise Ablehnung("unbekannt", "Dieses Modell gibt es im Verbund nicht.")
        if e.zweck.strip() or e.eignung or e.sprachen:
            await self.ablage.steckbriefe.speichern(e)
            self.steckbriefe_hand[e.familie] = e
        else:
            await self.ablage.steckbriefe.loeschen(e.familie)
            self.steckbriefe_hand.pop(e.familie, None)
        await self.ablage.pruefung.anhaengen(PruefEintrag(zeit_s=self.uhr.jetzt(), wer=wer, was="Steckbrief von Hand geändert", gegenstand=e.familie))
        self.geaendert()

    def _modell_abgleichen(self, kennung: str, d: Dienst, mb: ModellBericht, steuerbar: bool, jetzt: float) -> None:
        unbekannte_groesse = mb.parameter_mrd is None
        m = self.verbund.modelle.get(kennung)
        if m is None:
            m = Modell(kennung=kennung, name=mb.name, dienst=d.kennung, familie=mb.familie or mb.schluessel, faehigkeiten=set(mb.faehigkeiten), gb=mb.gb,
                       parameter_mrd=mb.parameter_mrd or 0.0, geschuetzt_fest=mb.einbettung or unbekannte_groesse)
            self.verbund.modelle[kennung] = m
        else:
            m.name, m.faehigkeiten, m.gb = mb.name, set(mb.faehigkeiten), mb.gb
            m.parameter_mrd, m.geschuetzt_fest = mb.parameter_mrd or 0.0, mb.einbettung or unbekannte_groesse
        m.schutz_vorgabe, m.gb_jetzt, m.plaetze = mb.schutz, mb.gb_jetzt, mb.plaetze
        # Einbettungsmodelle eines steuerbaren Läufers: Höchstzahl der Instanzen aus dem Eintrag des Dienstes (ZUSAMMENSPIEL Z5)
        eigene = d.einbettung_instanzen if mb.einbettung and steuerbar and not d.extern else 1
        m.instanzen_hoechstens, m.zusatz = max(mb.instanzen_hoechstens, eigene), mb.familie is not None
        if mb.aktiv:
            m.letzte_nutzung_s = jetzt      # arbeitet ohne Auftrag über die Leitstelle: gilt als genutzt, weicht nicht
        ort = self.orte.setdefault(kennung, ModellOrt(schluessel=mb.schluessel))
        ort.kontext = mb.kontext
        self.auskunft[kennung] = mb.selbstauskunft
        if mb.instanzen or not steuerbar:
            ort.instanzen = list(mb.instanzen)
        if not steuerbar or d.extern:
            # Der Dienst lädt selbst; für die Leitstelle ist das Modell immer verfügbar
            if m.zustand == Modellzustand.FREI:
                m.zustand = Modellzustand.GELADEN
                m.geladen_seit_s, m.letzte_nutzung_s = None, jetzt
            return
        if mb.geladen and m.zustand == Modellzustand.FREI:
            # Wann es geladen wurde, weiß die Leitstelle nicht: keine Mindestverweildauer (die schützt nur vor eigenem
            # Hin und Her). Wann zuletzt genutzt, auch nicht: als gerade genutzt werten, dann schützt die Bedarfsfrist.
            m.zustand = Modellzustand.GELADEN
            m.geladen_seit_s, m.letzte_nutzung_s = None, jetzt
            self.melden(f"{m.name} auf {d.name} ist geladen (von außen oder beim Start der Leitstelle)")
        elif not mb.geladen and m.zustand == Modellzustand.GELADEN and kennung not in self.ladeaufgaben:
            m.zustand = Modellzustand.FREI
            m.geladen_seit_s = None
            ort.instanzen = []
            self.melden(f"{m.name} auf {d.name} wurde vom Dienst selbst entladen")

    # ── Takt ─────────────────────────────────────────────────────────────
    async def _takt_schleife(self) -> None:
        while True:
            try:
                await asyncio.sleep(1.0)
                await self.takt()
            except asyncio.CancelledError:
                raise
            except Exception:                        # der Takt darf nie sterben
                log.exception("Fehler im Takt")

    async def takt(self) -> None:
        jetzt = self.uhr.jetzt()
        if jetzt - self._letzter_abgleich >= self.konfig.dienst_takt_s:
            await self.abgleichen()
        self._zeit_setzen()
        if jetzt - self._letzte_umschichtung >= self.verbund.regelwerk.umschichter_takt_s:
            self._letzte_umschichtung = jetzt
            self.kern.takt(self.verbund, self.messwerk, self)
            self._nach_kern()
        else:
            self.anstossen()
        for a in self.verbund.auftraege.values():
            if a.zustand == Auftragszustand.LAEUFT and a.start_s is not None:
                a.fortschritt_s = jetzt - a.start_s
        if jetzt - self._letzte_messung >= self.konfig.steckbrief_takt_s:
            self._letzte_messung = jetzt
            self._nebenbei(self._messwerte_holen())
        self.bus.senden(umschlag("leitstelle.takt", {"zeit_s": jetzt}))

    def _zeit_setzen(self) -> None:
        self.verbund.zeit_s = self.uhr.jetzt()
        self.verbund.stunde = self.uhr.stunde()

    def anstossen(self) -> None:
        """Sofort zuteilen und freigeben, was bereit ist (nach neuem Auftrag, Ende, Laden)."""
        self._zeit_setzen()
        self.kern.zuteilen(self.verbund, self.messwerk, self)
        self._nach_kern()

    def _nach_kern(self) -> None:
        for a in list(self.verbund.auftraege.values()):
            lauf = self.laeufe.get(a.kennung)
            if a.zustand == Auftragszustand.ABGELEHNT and lauf:
                lauf.beenden_mit(a.grund or "kein_dienst", a.begruendung, self._schlafzusatz(a.schlafende_knoten))
        self._massnahmen_uebernehmen()
        self.verbund.ereignisse.clear()
        self._starten_was_bereit()
        for a in self.verbund.auftraege.values():
            lauf = self.laeufe.get(a.kennung)
            if lauf:
                lauf.notieren(self.verbund.zeit_s, a.zustand, self._schritttext(a))
        self.geaendert()

    def _schlafzusatz(self, knoten: list[str]) -> Zusatz | None:
        """Die Namen schlafender Rechner für die Anwendung (error.x-leitstelle.rechner)."""
        return Zusatz(rechner=[self.verbund.knoten[k].name for k in knoten if k in self.verbund.knoten]) if knoten else None

    def _schritttext(self, a: Auftrag) -> str:
        if a.zustand == Auftragszustand.LAEUFT:
            m = self.verbund.modelle.get(a.modell or "")
            d = self.verbund.dienste.get(a.dienst or "")
            return f"rechnet mit {m.name if m else 'dem Modell'} auf {d.name if d else 'dem Dienst'}"
        return a.begruendung

    def _massnahmen_uebernehmen(self) -> None:
        jetzt = self.verbund.zeit_s
        fenster = self.verbund.regelwerk.fenster_s
        for m in self.verbund.massnahmen:
            if m.zustand in (Massnahmenzustand.AUSGEFUEHRT, Massnahmenzustand.GEPLANT):
                pass
            elif m.zustand == Massnahmenzustand.GESPERRT:
                schluessel = (m.regel, tuple(m.auftraege), m.grund)
                if jetzt - self._gesperrt_gemeldet.get(schluessel, -1e18) < fenster:
                    continue
                self._gesperrt_gemeldet[schluessel] = jetzt
            else:
                continue
            self.massnahmen.appendleft(m)
            self.schreibfolge.einreihen(self.ablage.massnahmen.speichern(m))
            self.bus.senden(umschlag("leitstelle.massnahme", m))
        self.verbund.massnahmen.clear()
        self._gesperrt_gemeldet = {k: z for k, z in self._gesperrt_gemeldet.items() if jetzt - z < fenster}

    def _starten_was_bereit(self) -> None:
        v = self.verbund
        bereit = sorted((a for a in v.auftraege.values() if a.zustand == Auftragszustand.ZUGETEILT), key=lambda a: (-int(a.prioritaet), a.eingang_s))
        for a in bereit:
            m = v.modelle.get(a.modell or "")
            d = v.dienste.get(a.dienst or "")
            if m is None or d is None or not d.nutzbar or m.zustand not in (Modellzustand.GELADEN, Modellzustand.RECHNET):
                continue
            if m.auftraege_aktiv >= v.plaetze(m):
                continue
            a.zustand = Auftragszustand.LAEUFT
            a.start_s = v.zeit_s
            m.auftraege_aktiv += 1
            m.zustand = Modellzustand.RECHNET
            m.letzte_nutzung_s = v.zeit_s
            lauf = self.laeufe.get(a.kennung)
            if lauf:
                lauf.freigabe.set()

    # ── Aufträge ─────────────────────────────────────────────────────────
    def anlegen(self, anwendung: str, faehigkeit: Faehigkeit, festes_modell: str | None, prioritaet: Prioritaet | None, titel: str,
                arbeit: str | None = None, extern: list[str] | None = None, instanz: str | None = None) -> tuple[Auftrag, Lauf]:
        app = self.anwendungen[anwendung]
        if self.verbund.betriebsmodus == Betriebsmodus.HALT:
            raise Ablehnung("halt", "Der Hauptregler steht auf Halt; es wird nichts gerechnet.")
        if app.gesperrt:
            raise Ablehnung("gesperrt", app.sperrgrund or "Die Anwendung ist gesperrt.")
        self._zeit_setzen()
        a = Auftrag(kennung=uuid4().hex, anwendung=anwendung, faehigkeit=faehigkeit, prioritaet=app.prioritaet if prioritaet is None else prioritaet,
                    eingang_s=self.verbund.zeit_s, festes_modell=festes_modell, anhaltbar=False, laufzeit_s=0.0,
                    arbeit=f"{anwendung}:{arbeit}" if arbeit else None, extern_familien=list(extern or []), feste_instanz=instanz)
        self.verbund.arbeiten_aufraeumen()
        self.verbund.arbeit_zaehlen(a, titel)
        lauf = Lauf(a.kennung, titel)
        lauf.notieren(a.eingang_s, Auftragszustand.EINGEREIHT, f"angenommen von {app.name}" + (f", Modell {festes_modell} verlangt" if festes_modell else ""))
        self.verbund.auftraege[a.kennung] = a
        self.laeufe[a.kennung] = lauf
        self.anstossen()
        self.schreibfolge.einreihen(self.ablage.auftraege.speichern(self._eintrag(a, lauf, Messung())))
        self.bus.senden(umschlag("auftrag.angenommen", {"auftrag": a.kennung, "anwendung": anwendung, "zustand": a.zustand.value,
                                                        "faehigkeit": faehigkeit.value, "titel": titel}))
        return a, lauf

    def abschliessen(self, kennung: str, zustand: Auftragszustand, messung: Messung, grund: str | None = None, begruendung: str | None = None) -> None:
        """Ende eines Auftrags: Modell freigeben, messen, speichern, weiter zuteilen."""
        a = self.verbund.auftraege.get(kennung)
        lauf = self.laeufe.pop(kennung, None)
        if a is None:
            return
        self._zeit_setzen()
        jetzt = self.verbund.zeit_s
        if a.zustand == Auftragszustand.LAEUFT and a.modell in self.verbund.modelle:
            m = self.verbund.modelle[a.modell]
            m.auftraege_aktiv = max(0, m.auftraege_aktiv - 1)
            m.letzte_nutzung_s = jetzt
            if m.auftraege_aktiv == 0 and m.zustand == Modellzustand.RECHNET:
                m.zustand = Modellzustand.GELADEN
            self.verbund.arbeit_nutzte(a)
        if zustand == Auftragszustand.FERTIG and a.start_s is not None:
            self.messwerk.merke_laufzeit(a.anwendung, a.faehigkeit.value, jetzt - a.start_s)
            self.schreibfolge.einreihen(self.ablage.messungen.speichern(self.messwerk))
        a.zustand = zustand
        a.ende_s = jetzt
        a.grund = grund
        if begruendung:
            a.begruendung = begruendung
        a.teilergebnis = messung.teilergebnis_zeichen > 0 and zustand != Auftragszustand.FERTIG
        if lauf:
            dauer = f" nach {komma(jetzt - a.start_s)} s" if a.start_s is not None else ""
            lauf.notieren(jetzt, zustand, (begruendung or {Auftragszustand.FERTIG: "fertig"}.get(zustand, grund or "")) + dauer)
        self.schreibfolge.einreihen(self.ablage.auftraege.speichern(self._eintrag(a, lauf, messung)))
        art = {Auftragszustand.FERTIG: "auftrag.ergebnis", Auftragszustand.ABGEBROCHEN: "auftrag.abgebrochen"}.get(zustand, "auftrag.fehler")
        m = self.verbund.modelle.get(a.modell or "")
        self.bus.senden(umschlag(art, {"auftrag": kennung, "zustand": zustand.value, "grund": grund, "teilergebnis": a.teilergebnis,
                                       "anwendung": a.anwendung, "titel": lauf.titel if lauf else "", "faehigkeit": a.faehigkeit.value,
                                       "modell": m.name if m else None, "knoten": a.knoten, "extern": a.extern,
                                       "dauer_s": round(jetzt - a.start_s, 3) if a.start_s is not None else None}))
        del self.verbund.auftraege[kennung]
        if lauf and lauf.danach_sperren:
            self._nebenbei(self.anwendung_sperren(a.anwendung, lauf.danach_sperren, "leitstelle"))
        self.anstossen()

    def _eintrag(self, a: Auftrag, lauf: Lauf | None, messung: Messung) -> AuftragEintrag:
        m = self.verbund.modelle.get(a.modell or "")
        return AuftragEintrag(kennung=a.kennung, anwendung=a.anwendung, faehigkeit=a.faehigkeit, prioritaet=a.prioritaet, titel=lauf.titel if lauf else "",
                              zustand=a.zustand, grund=a.grund, begruendung=a.begruendung, festes_modell=a.festes_modell, familie=m.familie if m else None,
                              modell_name=m.name if m else None, dienst=a.dienst, knoten=a.knoten, extern=a.extern, umgeleitet=a.umgeleitet,
                              eingang_s=a.eingang_s, start_s=a.start_s, ende_s=a.ende_s, erstes_stueck_s=messung.erstes_stueck_s,
                              token_ein=messung.token_ein, token_aus=messung.token_aus, teilergebnis_zeichen=messung.teilergebnis_zeichen,
                              schritte=list(lauf.schritte) if lauf else [], arbeit=a.arbeit)

    def ort(self, modell: str) -> ModellOrt:
        return self.orte.get(modell) or ModellOrt(schluessel=self.verbund.modelle[modell].familie)

    def knoten_ohne_meldung(self) -> list[str]:
        """Rechner, deren Dienste die Leitstelle (noch) nicht kennt: mit eingetragenem Maschinenraum nach ihrem Neustart,
        bis er sich meldet, und jeder Rechner, der seitdem schläft. Ein Name, den sie dann nicht kennt, kann dort liegen."""
        aus: list[str] = []
        for d in self.dienste.values():
            if not d.knoten or any(m.dienst == d.kennung for m in self.verbund.modelle.values()):
                continue
            k = self.verbund.knoten.get(d.knoten)
            if (d.art == Adapterart.AGENT or (k is not None and k.schlaeft)) and d.knoten not in aus:
                aus.append(d.knoten)
        return aus

    def unbekannt(self, name: str, was: str = "Modell") -> Ablehnung:
        """Die Ablehnung für einen unbekannten Namen: endgültig (kein_modell) nur, wenn sich alle Maschinenräume gemeldet
        haben; schlafen die übrigen, wartet die App, bis einer wach ist; sonst "nicht erreichbar" mit kurzer Wartezeit,
        damit Apps nach dem Neustart der Leitstelle nicht aufgeben."""
        fehlend = self.knoten_ohne_meldung()
        if not fehlend:
            return Ablehnung("kein_modell", f"{was} {name} ist im Verbund nicht bekannt.")
        schlafend = [k for k in fehlend if k in self.verbund.knoten and self.verbund.knoten[k].schlaeft]
        if len(schlafend) == len(fehlend):
            namen = [self.verbund.knoten[k].name for k in schlafend]
            return Ablehnung("rechner_schlaeft", schlaf_satz(namen), Zusatz(rechner=namen))
        namen = [self.knoten[k].name if k in self.knoten else k for k in fehlend if k not in schlafend]
        return Ablehnung("dienst_nicht_erreichbar", f"{was} {name} ist noch nicht gemeldet: der Maschinenraum auf "
                                                    f"{', '.join(namen)} hat sich noch nicht gemeldet; gleich erneut versuchen.")

    def familie_fuer(self, name: str) -> str | None:
        """Löst einen Modellnamen der Anwendung auf: eigener Alias, Schlüssel, Instanz, Name ohne Anbieter, Anzeigename."""
        if not name:
            return None
        if name in self.aliasse:
            return self.aliasse[name]
        klein = name.lower()
        for kennung, m in self.verbund.modelle.items():
            ort = self.orte.get(kennung)
            if name == m.familie or (ort and name in ort.instanzen):
                return m.familie
        for m in self.verbund.modelle.values():
            if klein in (m.familie.lower(), m.familie.lower().split("/")[-1], m.name.lower()):
                return m.familie
        return None

    # ── Steuerung durch den Menschen ─────────────────────────────────────
    async def hauptregler(self, modus: Betriebsmodus, hintergrund_an: bool, wer: str, grund: str = "") -> int:
        """Stellt den Hauptregler. Halt bricht alles ab, was läuft oder wartet. Gibt die Zahl betroffener Aufträge zurück."""
        alt = self.verbund.betriebsmodus
        self.verbund.betriebsmodus = modus
        self.verbund.hintergrund_erlaubt = hintergrund_an
        betroffen = 0
        if modus == Betriebsmodus.HALT:
            for lauf in list(self.laeufe.values()):
                lauf.beenden_mit("halt", "Der Hauptregler wurde auf Halt gestellt." + (f" Grund: {grund}" if grund else ""))
                betroffen += 1
        elif modus == Betriebsmodus.AUSLAUFEN:
            betroffen = sum(1 for a in self.verbund.offene_auftraege() if a.wartet)
        await self.ablage.einstellungen.betrieb_speichern(BetriebEinstellung(modus=modus, hintergrund_an=hintergrund_an))
        await self.ablage.pruefung.anhaengen(PruefEintrag(zeit_s=self.uhr.jetzt(), wer=wer, was=f"Hauptregler {alt.value} auf {modus.value}, Hintergrund {'an' if hintergrund_an else 'aus'}" + (f", Grund: {grund}" if grund else "")))
        self.melden(f"Hauptregler: {modus.value}, Hintergrund {'an' if hintergrund_an else 'angehalten'}")
        self.bus.senden(umschlag("leitstelle.modus_gesetzt", {"modus": modus.value, "hintergrund": hintergrund_an, "betroffene_auftraege": betroffen}))
        self.anstossen()
        return betroffen

    async def stoppen(self, kennung: str, sofort: bool, grund: str, wer: str) -> None:
        """Sofort: abbrechen mit Teilergebnis. Auslaufen: fertig rechnen lassen, danach die Anwendung sperren."""
        lauf = self.laeufe.get(kennung)
        a = self.verbund.auftraege.get(kennung)
        if lauf is None or a is None:
            raise Ablehnung("unbekannt", "Dieser Auftrag ist nicht mehr offen.")
        await self.ablage.pruefung.anhaengen(PruefEintrag(zeit_s=self.uhr.jetzt(), wer=wer, was=f"Auftrag gestoppt ({'sofort' if sofort else 'auslaufen'})",
                                                          gegenstand=f"{self.anwendungen[a.anwendung].name} {kennung[:8]}"))
        if sofort:
            lauf.beenden_mit("nutzer", grund or "Vom Menschen in der Leitstelle sofort gestoppt.")
        else:
            lauf.danach_sperren = grund or "Nach dem Auslaufen eines Auftrags in der Leitstelle gesperrt."
            self.melden(f"Auftrag {kennung[:8]} läuft aus; danach wird {self.anwendungen[a.anwendung].name} gesperrt")
        self.geaendert()

    async def anwendung_sperren(self, kennung: str, grund: str, wer: str) -> None:
        a = self.anwendungen[kennung].model_copy(update={"gesperrt": True, "sperrgrund": grund})
        await self.ablage.anwendungen.speichern(a)
        await self.ablage.pruefung.anhaengen(PruefEintrag(zeit_s=self.uhr.jetzt(), wer=wer, was="Anwendung gesperrt: " + grund, gegenstand=a.name))
        self.anwendung_setzen(a)
        self.bus.senden(umschlag("signal.gesperrt", {"was": "anwendung", "grund": grund}, an=f"anwendung:{kennung}"))

    async def modell_von_hand(self, modell: str, laden: bool, wer: str) -> None:
        """Laden oder Entladen auf Wunsch des Menschen; der Speicherplan der Vorschau wurde vorher gezeigt."""
        m = self.verbund.modelle[modell]
        if laden:
            self._zeit_setzen()
            self.modell_laden(modell)
        else:
            if m.zustand == Modellzustand.RECHNET or self.verbund.belegung(modell):
                raise Ablehnung("nicht_anhaltbar", f"{m.name} rechnet gerade; es wird nicht unter einem laufenden Auftrag entladen.")
            self.modell_entladen(modell)
        await self.ablage.pruefung.anhaengen(PruefEintrag(zeit_s=self.uhr.jetzt(), wer=wer, was=f"Modell von Hand {'geladen' if laden else 'entladen'}", gegenstand=m.name))
        self.geaendert()

    async def speicher_freigeben(self, knoten: str, vorschau: bool, wer: str) -> list[Freigabe]:
        """Was auf dem Rechner jetzt entladen werden darf und warum der Rest bleibt. Ohne Vorschau wird entladen."""
        from ..kern.speicherplaner import entladbar
        if knoten not in self.verbund.knoten:
            raise Ablehnung("unbekannt", "Diesen Rechner gibt es nicht.")
        self._zeit_setzen()
        plan = []
        for m in sorted(self.verbund.modelle_auf(knoten), key=lambda x: -x.gb):
            if not m.im_speicher:
                continue
            darf, grund = entladbar(self.verbund, m, self.verbund.zeit_s, nur_leerlauf=False)
            plan.append(Freigabe(modell=m.kennung, name=m.name, gb=m.gb, darf=darf, grund=grund))
        if not vorschau:
            for f in plan:
                if f.darf:
                    self.modell_entladen(f.modell)
            frei = sum(f.gb for f in plan if f.darf)
            await self.ablage.pruefung.anhaengen(PruefEintrag(zeit_s=self.uhr.jetzt(), wer=wer, was=f"Speicher freigegeben: {komma(frei)} GB",
                                                              gegenstand=self.verbund.knoten[knoten].name))
            self.anstossen()
        return plan

    # ── Vollzug: was der Kern beschließt ─────────────────────────────────
    def dienst_starten(self, dienst: str) -> None:
        d = self.verbund.dienste[dienst]
        self.melden(f"{d.name} kann nicht gestartet werden: auf dem Rechner läuft kein Maschinenraum")

    def modell_laden(self, modell: str) -> None:
        m = self.verbund.modelle[modell]
        d = self.verbund.dienste[m.dienst]
        if d.extern or not self.steuerbar.get(d.kennung, False):
            m.zustand = Modellzustand.GELADEN
            return
        if m.zustand != Modellzustand.FREI or modell in self.ladeaufgaben:
            return
        m.zustand = Modellzustand.LAEDT
        m.geladen_seit_s = self.verbund.zeit_s
        self.ladeaufgaben[modell] = asyncio.create_task(self._laden(modell), name=f"laden-{modell[:8]}")
        self.bus.senden(umschlag("signal.modell", {"modell": m.name, "zustand": "wird_geladen", "knoten": d.knoten,
                                                  "dauer_s": self.messwerk.ladezeit(m.familie, d.knoten or "", m.gb).sekunden}))
        self.geaendert()

    def instanz_starten(self, dienst: str, familie: str, vorbild: str) -> None:
        """Weitere Instanz (ZUSAMMENSPIEL Z3, Z5): im Verbund sofort als ladend eingeplant, damit ihr Speicher zählt;
        geplant unter `<familie>.<stufe>` (kleinste freie Stufe ab 2). Der Dienst startet sie (Maschinenraum unter diesem
        Namen, Modell-Läufer mit eigener Kennung) und meldet sie danach selbst."""
        v = self.verbund.modelle[vorbild]
        stufe = next(n for n in range(2, 1000) if modell_kennung(dienst, f"{familie}.{n}") not in self.verbund.modelle)
        schluessel = f"{familie}.{stufe}"
        kennung = modell_kennung(dienst, schluessel)
        self.verbund.modelle[kennung] = Modell(kennung=kennung, name=f"{v.name} ({stufe})", dienst=dienst, familie=familie, faehigkeiten=set(v.faehigkeiten),
                                               gb=v.gb, parameter_mrd=v.parameter_mrd, geschuetzt_fest=False, schutz_vorgabe=v.schutz_vorgabe,
                                               instanzen_hoechstens=v.instanzen_hoechstens, zusatz=True, plaetze=v.plaetze)
        self.orte[kennung] = ModellOrt(schluessel=schluessel, weitere=(self.ort(vorbild).schluessel, stufe))
        self.modell_laden(kennung)

    async def _laden(self, modell: str) -> None:
        m = self.verbund.modelle[modell]
        d = self.verbund.dienste[m.dienst]
        if laufend := self.entladungen.get(d.knoten or ""):
            # Erst frei, dann laden: was für dieses Laden weicht, muss den Speicher wirklich hergegeben haben
            await asyncio.gather(*laufend, return_exceptions=True)
        start = self.uhr.jetzt()
        try:
            ort = self.ort(modell)
            adapter = self.adapter[d.kennung]
            instanz = await (adapter.instanz_laden(*ort.weitere) if ort.weitere else adapter.laden(ort.schluessel))
        except DienstFehler as f:
            self._bewegung(modell, Richtung.LADEN, start, Ausgang.ABGELEHNT, f.meldung)
            self._laden_gescheitert(modell, f)
        else:
            dauer = self.uhr.jetzt() - start
            self._bewegung(modell, Richtung.LADEN, start)
            self.orte.setdefault(modell, ModellOrt(schluessel=m.familie)).instanzen = [instanz]
            if m.zustand == Modellzustand.LAEDT:
                m.zustand = Modellzustand.GELADEN
            m.geladen_seit_s = m.letzte_nutzung_s = self.uhr.jetzt()
            m.ladesperre_bis_s, m.ladesperre_grund = None, ""
            self.ladeversuche.pop(modell, None)
            self.messwerk.merke_ladezeit(m.familie, d.knoten or "", dauer)
            self.schreibfolge.einreihen(self.ablage.messungen.speichern(self.messwerk))
            self.melden(f"{m.name} auf {d.name} geladen in {komma(dauer)} s")
            self.bus.senden(umschlag("signal.modell", {"modell": m.name, "zustand": "bereit", "knoten": d.knoten, "dauer_s": round(dauer, 1)}))
        finally:
            self.ladeaufgaben.pop(modell, None)
            self.anstossen()

    def _laden_gescheitert(self, modell: str, f: DienstFehler) -> None:
        m = self.verbund.modelle[modell]
        d = self.verbund.dienste[m.dienst]
        jetzt = self.uhr.jetzt()
        versuch = self.ladeversuche.get(modell, 0)
        self.ladeversuche[modell] = versuch + 1
        pause = LADEPAUSEN_S[min(versuch, len(LADEPAUSEN_S) - 1)]
        m.zustand = Modellzustand.FREI
        m.geladen_seit_s = None
        m.ladesperre_bis_s = jetzt + pause
        m.ladesperre_grund = "zu wenig Speicher" if f.grund == "modell_passt_nicht" else f.meldung[:160]
        self.melden(f"{d.name} hat das Laden von {m.name} abgelehnt ({m.ladesperre_grund}); neuer Versuch frühestens in {pause:.0f} s")
        for a in self.verbund.auftraege.values():
            if a.modell == modell and a.zustand == Auftragszustand.ZUGETEILT:
                lauf = self.laeufe.get(a.kennung)
                a.zustand = Auftragszustand.EINGEREIHT
                a.dienst = a.modell = a.knoten = None
                if lauf:
                    lauf.ladefehler += 1
                    if lauf.ladefehler >= LADEFEHLER_BIS_ABBRUCH:
                        lauf.beenden_mit(f.grund, f"{d.name} hat das Laden von {m.name} {lauf.ladefehler}-mal abgelehnt: {f.meldung}")

    def modell_entladen(self, modell: str) -> None:
        m = self.verbund.modelle[modell]
        d = self.verbund.dienste[m.dienst]
        if m.zustand == Modellzustand.RECHNET or self.verbund.belegung(modell):
            log.error("Entladen eines belegten Modells verweigert: %s", m.name)
            return
        if d.extern or not self.steuerbar.get(d.kennung, False):
            return
        instanzen = list(self.ort(modell).instanzen)
        m.zustand = Modellzustand.FREI
        m.geladen_seit_s = None
        if modell in self.orte:
            self.orte[modell].instanzen = []
        if d.knoten:
            laufend = self.entladungen.setdefault(d.knoten, set())
            t = self._nebenbei(self._entladen(modell, instanzen))
            laufend.add(t)
            t.add_done_callback(laufend.discard)
        else:
            self._nebenbei(self._entladen(modell, instanzen))
        self.bus.senden(umschlag("signal.modell", {"modell": m.name, "zustand": "entladen", "knoten": d.knoten}))
        self.geaendert()

    async def _entladen(self, modell: str, instanzen: list[str]) -> None:
        m = self.verbund.modelle[modell]
        for i in instanzen:
            start = self.uhr.jetzt()
            try:
                await self.adapter[m.dienst].entladen(i)
            except DienstFehler as f:
                self._bewegung(modell, Richtung.ENTLADEN, start, Ausgang.GESCHEITERT, f.meldung)
                self.melden(f"Entladen von {m.name} gescheitert: {f.meldung}; der nächste Abgleich zeigt den wahren Stand")
            else:
                self._bewegung(modell, Richtung.ENTLADEN, start)

    def _bewegung(self, modell: str, richtung: Richtung, start: float, ausgang: Ausgang = Ausgang.OK, meldung: str = "") -> None:
        """Laden und Entladen als Rohdatum in den Verlauf."""
        m = self.verbund.modelle[modell]
        knoten = self.verbund.dienste[m.dienst].knoten if m.dienst in self.verbund.dienste else None
        b = Bewegung(zeit_s=start, richtung=richtung, familie=m.familie, name=m.name, knoten=knoten, gb=m.gb,
                     dauer_s=round(self.uhr.jetzt() - start, 3), ausgang=ausgang, meldung=meldung[:300])
        self.schreibfolge.einreihen(self.ablage.bewegungen.anhaengen(b))

    def auftrag_umleiten(self, auftrag: str, dienst: str, modell: str, knoten: str | None) -> None:
        a = self.verbund.auftraege[auftrag]
        a.dienst, a.modell, a.knoten = dienst, modell, knoten
        a.umgeleitet += 1
        a.zustand = Auftragszustand.ZUGETEILT
        a.wartet_auf_familie = a.wartet_auf_knoten = None
        a.voraussichtlich_s = None
        if self.verbund.modelle[modell].zustand == Modellzustand.FREI:
            self.modell_laden(modell)

    def auftrag_extern(self, auftrag: str, dienst: str, modell: str) -> None:
        a = self.verbund.auftraege[auftrag]
        a.dienst, a.modell, a.knoten, a.extern = dienst, modell, None, True
        a.umgeleitet += 1
        a.zustand = Auftragszustand.ZUGETEILT
        a.wartet_auf_familie = a.wartet_auf_knoten = None
        m = self.verbund.modelle[modell]
        if m.zustand == Modellzustand.FREI:
            m.zustand = Modellzustand.GELADEN

    def melden(self, text: str) -> None:
        jetzt = self.uhr.jetzt()
        self.meldungen.appendleft((jetzt, text))
        log.info(text)
        self.bus.senden(umschlag("leitstelle.meldung", {"zeit_s": jetzt, "text": text}))
        self.geaendert()

    def signal(self, anwendung: str, art: str, nutzlast: dict) -> None:
        self.bus.senden(umschlag(art, nutzlast, an=f"anwendung:{anwendung}"))

    def laufende_abbrechen_mit_teilergebnis(self, knoten: str) -> None:
        """Regel "Umverteilen bei Ausfall"."""
        self._laufende_beenden(knoten, "dienst_nicht_erreichbar", f"{self.verbund.knoten[knoten].name} ist nicht mehr erreichbar.")

    def _laufende_beenden(self, knoten: str, grund: str, begruendung: str, zusatz: Zusatz | None = None) -> None:
        """Laufende Aufträge auf dem Rechner enden mit Teilergebnis, zugeteilte kommen zurück in die Warteschlange."""
        for a in list(self.verbund.auftraege.values()):
            if a.knoten != knoten:
                continue
            if a.zustand == Auftragszustand.LAEUFT and a.kennung in self.laeufe:
                self.laeufe[a.kennung].beenden_mit(grund, begruendung, zusatz)
            elif a.zustand == Auftragszustand.ZUGETEILT:
                a.zustand = Auftragszustand.EINGEREIHT
                a.dienst = a.modell = a.knoten = None

    def wartende_neu_einreihen(self, knoten: str) -> None:
        for a in self.verbund.auftraege.values():
            if a.wartet and (a.wartet_auf_knoten == knoten or a.knoten == knoten):
                a.zustand = Auftragszustand.EINGEREIHT
                a.dienst = a.modell = a.knoten = None
                a.wartet_auf_familie = a.wartet_auf_knoten = None
                a.voraussichtlich_s = None

    def bevorzugter_knoten(self, knoten: str | None) -> None:
        self.verbund.hintergrund_knoten_bevorzugt = knoten

    def hintergrund(self, an: bool) -> None:
        """Regel "Hintergrund bei Lage". Fassaden-Aufträge sind nicht anhaltbar; zurückgehalten wird nur, was
        noch nicht läuft (der Zuteiler tut das). Der Schalter am Hauptregler ist davon getrennt."""
        self.verbund.hintergrund_an = an
