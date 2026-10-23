"""Verzeichnis: Anschlussstellen (Rechner, Dienste) und Anwendungen einrichten, minimal-invasiv.

Der Mensch gibt nur an, was die Leitstelle nicht selbst erkennen kann: Adresse, bei Bedarf einen
Zugang, bei einem neuen Rechner dessen Speicher (bis der Knoten-Agent ihn misst). Art, Modelle und
Fähigkeiten erkennt die Leitstelle über eine Abfrage, die nichts verändert und nichts lädt.
Jede Änderung geht erst in die Ablage, dann in den Betrieb; Aufdecken von Geheimnissen steht im
Prüfprotokoll.
"""

from __future__ import annotations

from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field

from ..kern.werte import Faehigkeit, Prioritaet, Zone
from ..ports.ablage.eintraege import Adapterart, AliasEintrag, AnwendungEintrag, DienstEintrag, KnotenEintrag, PruefEintrag
from ..ports.dienste import ModellBericht
from ..ports.tresor import fingerabdruck, neuer_anwendungsschluessel
from .betrieb import Betrieb
from .fehler import Ablehnung


class KnotenDaten(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    adresse: str = Field(min_length=1, max_length=255)
    speicher_gb: float = Field(gt=0, le=4096)
    zone: Zone = Zone.HEIM
    system_gb: float = Field(default=6.0, ge=0, le=512)
    budget_fest_gb: float | None = Field(default=None, gt=0, le=4096)
    hintergrund_von: int | None = Field(default=None, ge=0, le=23)
    hintergrund_bis: int | None = Field(default=None, ge=0, le=23)


class Erkennung(BaseModel):
    erreichbar: bool
    steuerbar: bool
    meldung: str
    art: Adapterart
    adresse: str
    rechnername: str | None
    knoten_vorschlag: str | None          # vorhandener Rechner mit dieser Adresse
    name_vorschlag: str
    modelle: list[ModellBericht]


def _art(extern: bool) -> Adapterart:
    """Externe Anbieter sprechen OpenAI-Format, werden aber selten gefragt und nie gesteuert (ZUSAMMENSPIEL Z4)."""
    return Adapterart.EXTERN_OPENAI if extern else Adapterart.OPENAI_KOMPATIBEL


class DienstDaten(BaseModel):
    adresse: str = Field(min_length=8, max_length=255)
    name: str | None = Field(default=None, max_length=120)
    zugang: str | None = Field(default=None, max_length=500)   # Klartext nur auf dem Weg in den Tresor
    knoten: str | None = None
    neuer_knoten: KnotenDaten | None = None
    extern: bool = False
    plaetze: int = Field(default=4, ge=1, le=64)
    anfragen_je_minute: int | None = Field(default=None, ge=1, le=100000)   # Grenze des Anbieters
    abgleich_s: float | None = Field(default=None, ge=1, le=86400)         # Abstand der Zustandsabfrage, wenn gesund
    einbettung_instanzen: int = Field(default=1, ge=1, le=32)              # Instanzen je Einbettungsmodell bei Andrang
    einbettung_spielraum_gb: float = Field(default=4.0, ge=0, le=512)      # bleibt im Budget frei


class DienstAenderung(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    adresse: str | None = Field(default=None, max_length=255)
    zugang: str | None = Field(default=None, max_length=500)  # "" entfernt den Zugang, None lässt ihn
    plaetze: int | None = Field(default=None, ge=1, le=64)
    anfragen_je_minute: int | None = Field(default=None, ge=0, le=100000)  # 0 entfernt die Grenze, None lässt sie
    abgleich_s: float | None = Field(default=None, ge=0, le=86400)         # 0 heißt Vorgabe, None lässt ihn
    einbettung_instanzen: int | None = Field(default=None, ge=1, le=32)
    einbettung_spielraum_gb: float | None = Field(default=None, ge=0, le=512)


class AnwendungDaten(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    prioritaet: Prioritaet = Prioritaet.NORMAL
    faehigkeiten: set[Faehigkeit] = Field(default_factory=lambda: {Faehigkeit.TEXT, Faehigkeit.EINBETTUNG, Faehigkeit.UEBERSETZEN, Faehigkeit.BILD_BESCHREIBEN, Faehigkeit.WERKZEUG})
    zonen: set[Zone] = Field(default_factory=lambda: {Zone.HEIM})
    extern_erlaubt: bool = False
    gleichzeitig: int = Field(default=4, ge=1, le=64)
    ketten: dict[Faehigkeit, list[str]] = Field(default_factory=dict)


def _rechnername(adresse: str) -> str | None:
    return (urlparse(adresse).hostname or "").lower() or None


def _adresse_pruefen(adresse: str, extern: bool) -> str:
    adresse = adresse.strip().rstrip("/")
    teile = urlparse(adresse)
    if teile.scheme not in ("http", "https") or not teile.hostname:
        raise Ablehnung("adresse", "Die Adresse muss mit http:// oder https:// beginnen und einen Rechner nennen.")
    if extern and teile.scheme != "https":
        raise Ablehnung("adresse", "Externe Anbieter nur über https.")
    return adresse


class Verzeichnis:
    def __init__(self, betrieb: Betrieb) -> None:
        self.b = betrieb

    async def _pruefen(self, wer: str, was: str, gegenstand: str = "") -> None:
        await self.b.ablage.pruefung.anhaengen(PruefEintrag(zeit_s=self.b.uhr.jetzt(), wer=wer, was=was, gegenstand=gegenstand))

    # ── Rechner ──────────────────────────────────────────────────────────
    async def knoten_anlegen(self, d: KnotenDaten, wer: str) -> KnotenEintrag:
        k = KnotenEintrag(kennung=uuid4().hex, **d.model_dump())
        k.adresse = k.adresse.strip().lower()
        await self.b.ablage.knoten.speichern(k)
        self.b.knoten_setzen(k)
        await self._pruefen(wer, "Rechner eingerichtet", k.name)
        return k

    async def knoten_aendern(self, kennung: str, d: KnotenDaten, wer: str) -> KnotenEintrag:
        if kennung not in self.b.knoten:
            raise Ablehnung("unbekannt", "Diesen Rechner gibt es nicht.")
        k = self.b.knoten[kennung].model_copy(update=d.model_dump())
        k.adresse = k.adresse.strip().lower()
        await self.b.ablage.knoten.speichern(k)
        self.b.knoten_setzen(k)
        await self._pruefen(wer, "Rechner geändert", k.name)
        return k

    async def agent_schluessel_neu(self, kennung: str, wer: str) -> str:
        """Neuer Schlüssel für den Knoten-Agenten; ein verbundener Agent mit dem alten Schlüssel wird getrennt."""
        k = self.b.knoten.get(kennung)
        if k is None:
            raise Ablehnung("unbekannt", "Diesen Rechner gibt es nicht.")
        schluessel = neuer_anwendungsschluessel()
        neu = k.model_copy(update={"agent_fingerabdruck": fingerabdruck(schluessel), "agent_geheim": self.b.tresor.verschluesseln(schluessel)})
        await self.b.ablage.knoten.speichern(neu)
        self.b.knoten_setzen(neu)
        v = self.b.agenten.verbindung(kennung)
        if v and v.beenden:
            await v.beenden()
        await self._pruefen(wer, "Schlüssel für den Maschinenraum neu erzeugt" if k.agent_fingerabdruck else "Schlüssel für den Maschinenraum erzeugt", k.name)
        return schluessel

    async def agent_schluessel_zeigen(self, kennung: str, wer: str) -> str:
        k = self.b.knoten.get(kennung)
        if k is None or not k.agent_geheim:
            raise Ablehnung("unbekannt", "Für diesen Rechner gibt es noch keinen Schlüssel für den Maschinenraum.")
        await self._pruefen(wer, "Schlüssel für den Maschinenraum aufgedeckt", k.name)
        return self.b.tresor.entschluesseln(k.agent_geheim)

    async def knoten_loeschen(self, kennung: str, wer: str) -> None:
        k = self.b.knoten.get(kennung)
        if k is None:
            raise Ablehnung("unbekannt", "Diesen Rechner gibt es nicht.")
        if any(d.knoten == kennung for d in self.b.dienste.values()):
            raise Ablehnung("in_gebrauch", f"Auf {k.name} sind noch Dienste eingerichtet; erst die Dienste entfernen.")
        await self.b.ablage.knoten.loeschen(kennung)
        self.b.knoten_entfernen(kennung)
        await self._pruefen(wer, "Rechner entfernt", k.name)

    # ── Dienste ──────────────────────────────────────────────────────────
    async def erkennen(self, adresse: str, zugang: str | None = None, extern: bool = False) -> Erkennung:
        adresse = _adresse_pruefen(adresse, extern)
        art = _art(extern)
        adapter = self.b.fabrik(art, adresse, zugang or None, None)
        try:
            bericht = await adapter.zustand()
        finally:
            await adapter.schliessen()
        rechner = _rechnername(adresse)
        vorschlag = next((k.kennung for k in self.b.knoten.values() if k.adresse == rechner), None)
        return Erkennung(erreichbar=bericht.erreichbar, steuerbar=bericht.steuerbar, meldung=bericht.meldung, art=art,
                         adresse=adresse, rechnername=rechner, knoten_vorschlag=vorschlag,
                         name_vorschlag=("Modell-Läufer " + (self.b.knoten[vorschlag].name if vorschlag else (rechner or adresse))) if not extern else (rechner or adresse),
                         modelle=bericht.modelle)

    async def dienst_anlegen(self, d: DienstDaten, wer: str) -> DienstEintrag:
        adresse = _adresse_pruefen(d.adresse, d.extern)
        knoten = None
        if not d.extern:
            if d.neuer_knoten:
                knoten = (await self.knoten_anlegen(d.neuer_knoten, wer)).kennung
            elif d.knoten:
                if d.knoten not in self.b.knoten:
                    raise Ablehnung("unbekannt", "Diesen Rechner gibt es nicht.")
                knoten = d.knoten
            else:
                raise Ablehnung("knoten_fehlt", "Ein Dienst im eigenen Netz gehört zu einem Rechner; Rechner wählen oder neu einrichten.")
        rechner = _rechnername(adresse) or adresse
        e = DienstEintrag(kennung=uuid4().hex, name=d.name or ("Modell-Läufer " + (self.b.knoten[knoten].name if knoten else rechner)),
                          art=_art(d.extern), adresse=adresse, knoten=knoten, extern=d.extern,
                          zugang_geheim=self.b.tresor.verschluesseln(d.zugang) if d.zugang else None, plaetze=d.plaetze,
                          anfragen_je_minute=d.anfragen_je_minute, abgleich_s=d.abgleich_s,
                          einbettung_instanzen=d.einbettung_instanzen, einbettung_spielraum_gb=d.einbettung_spielraum_gb)
        await self.b.ablage.dienste.speichern(e)
        self.b.dienst_setzen(e)
        await self._pruefen(wer, "Dienst eingerichtet" + (" mit Zugang" if d.zugang else ""), e.name)
        await self.b.abgleichen()
        return e

    async def dienst_aendern(self, kennung: str, d: DienstAenderung, wer: str) -> DienstEintrag:
        e = self.b.dienste.get(kennung)
        if e is None:
            raise Ablehnung("unbekannt", "Diesen Dienst gibt es nicht.")
        neu = e.model_copy()
        if d.name:
            neu.name = d.name
        if d.adresse:
            neu.adresse = _adresse_pruefen(d.adresse, e.extern)
        if d.plaetze:
            neu.plaetze = d.plaetze
        if d.anfragen_je_minute is not None:
            neu.anfragen_je_minute = d.anfragen_je_minute or None
        if d.abgleich_s is not None:
            neu.abgleich_s = d.abgleich_s or None
        if d.einbettung_instanzen is not None:
            neu.einbettung_instanzen = d.einbettung_instanzen
        if d.einbettung_spielraum_gb is not None:
            neu.einbettung_spielraum_gb = d.einbettung_spielraum_gb
        if d.zugang is not None:
            neu.zugang_geheim = self.b.tresor.verschluesseln(d.zugang) if d.zugang else None
        await self.b.ablage.dienste.speichern(neu)
        self.b.dienst_setzen(neu)
        await self._pruefen(wer, "Dienst geändert" + (" (Zugang neu)" if d.zugang else " (Zugang entfernt)" if d.zugang == "" else ""), neu.name)
        await self.b.abgleichen()
        return neu

    async def dienst_loeschen(self, kennung: str, wer: str) -> None:
        e = self.b.dienste.get(kennung)
        if e is None:
            raise Ablehnung("unbekannt", "Diesen Dienst gibt es nicht.")
        if any(a.dienst == kennung for a in self.b.verbund.offene_auftraege()):
            raise Ablehnung("in_gebrauch", f"{e.name} hat offene Aufträge; erst auslaufen lassen.")
        await self.b.ablage.dienste.loeschen(kennung)
        self.b.dienst_entfernen(kennung)
        await self._pruefen(wer, "Dienst entfernt", e.name)

    async def dienst_zugang_zeigen(self, kennung: str, wer: str) -> str | None:
        e = self.b.dienste.get(kennung)
        if e is None:
            raise Ablehnung("unbekannt", "Diesen Dienst gibt es nicht.")
        await self._pruefen(wer, "Zugang aufgedeckt", e.name)
        return self.b.tresor.entschluesseln(e.zugang_geheim) if e.zugang_geheim else None

    # ── Anwendungen ──────────────────────────────────────────────────────
    def _ketten_pruefen(self, ketten: dict[Faehigkeit, list[str]]) -> dict[Faehigkeit, list[str]]:
        aus: dict[Faehigkeit, list[str]] = {}
        for f, namen in ketten.items():
            familien = []
            for n in namen:
                fam = self.b.familie_fuer(n) or n
                if fam not in familien:
                    familien.append(fam)
            if familien:
                aus[f] = familien
        return aus

    async def anwendung_anlegen(self, d: AnwendungDaten, wer: str) -> tuple[AnwendungEintrag, str]:
        if any(a.name.lower() == d.name.strip().lower() for a in self.b.anwendungen.values()):
            raise Ablehnung("doppelt", f"Eine Anwendung namens {d.name} gibt es schon.")
        schluessel = neuer_anwendungsschluessel()
        a = AnwendungEintrag(kennung=uuid4().hex, name=d.name.strip(), schluessel_fingerabdruck=fingerabdruck(schluessel),
                             schluessel_geheim=self.b.tresor.verschluesseln(schluessel), prioritaet=d.prioritaet, faehigkeiten=d.faehigkeiten,
                             zonen=d.zonen | {Zone.EXTERN} if d.extern_erlaubt else d.zonen - {Zone.EXTERN}, extern_erlaubt=d.extern_erlaubt,
                             gleichzeitig=d.gleichzeitig, ketten=self._ketten_pruefen(d.ketten), angelegt_s=self.b.uhr.jetzt())
        await self.b.ablage.anwendungen.speichern(a)
        self.b.anwendung_setzen(a)
        await self._pruefen(wer, "Anwendung angelegt, Schlüssel erzeugt", a.name)
        return a, schluessel

    async def anwendung_aendern(self, kennung: str, d: AnwendungDaten, wer: str) -> AnwendungEintrag:
        alt = self.b.anwendungen.get(kennung)
        if alt is None:
            raise Ablehnung("unbekannt", "Diese Anwendung gibt es nicht.")
        zonen = d.zonen | {Zone.EXTERN} if d.extern_erlaubt else d.zonen - {Zone.EXTERN}
        a = alt.model_copy(update={"name": d.name.strip(), "prioritaet": d.prioritaet, "faehigkeiten": d.faehigkeiten, "zonen": zonen,
                                   "extern_erlaubt": d.extern_erlaubt, "gleichzeitig": d.gleichzeitig, "ketten": self._ketten_pruefen(d.ketten)})
        await self.b.ablage.anwendungen.speichern(a)
        self.b.anwendung_setzen(a)
        await self._pruefen(wer, "Anwendung geändert", a.name)
        return a

    async def anwendung_schluessel_zeigen(self, kennung: str, wer: str) -> str:
        a = self.b.anwendungen.get(kennung)
        if a is None:
            raise Ablehnung("unbekannt", "Diese Anwendung gibt es nicht.")
        await self._pruefen(wer, "Schlüssel aufgedeckt", a.name)
        return self.b.tresor.entschluesseln(a.schluessel_geheim)

    async def anwendung_schluessel_neu(self, kennung: str, wer: str) -> str:
        a = self.b.anwendungen.get(kennung)
        if a is None:
            raise Ablehnung("unbekannt", "Diese Anwendung gibt es nicht.")
        schluessel = neuer_anwendungsschluessel()
        neu = a.model_copy(update={"schluessel_fingerabdruck": fingerabdruck(schluessel), "schluessel_geheim": self.b.tresor.verschluesseln(schluessel)})
        await self.b.ablage.anwendungen.speichern(neu)
        self.b.anwendung_setzen(neu)
        await self._pruefen(wer, "Schlüssel neu erzeugt, der alte gilt nicht mehr", a.name)
        return schluessel

    async def anwendung_freigeben(self, kennung: str, wer: str) -> AnwendungEintrag:
        a = self.b.anwendungen.get(kennung)
        if a is None:
            raise Ablehnung("unbekannt", "Diese Anwendung gibt es nicht.")
        neu = a.model_copy(update={"gesperrt": False, "sperrgrund": ""})
        await self.b.ablage.anwendungen.speichern(neu)
        self.b.anwendung_setzen(neu)
        await self._pruefen(wer, "Anwendung freigegeben", a.name)
        return neu

    async def anwendung_sperren(self, kennung: str, grund: str, wer: str) -> None:
        if kennung not in self.b.anwendungen:
            raise Ablehnung("unbekannt", "Diese Anwendung gibt es nicht.")
        await self.b.anwendung_sperren(kennung, grund or "Von Hand in der Leitstelle gesperrt.", wer)

    async def anwendung_loeschen(self, kennung: str, wer: str) -> None:
        a = self.b.anwendungen.get(kennung)
        if a is None:
            raise Ablehnung("unbekannt", "Diese Anwendung gibt es nicht.")
        if any(x.anwendung == kennung for x in self.b.verbund.offene_auftraege()):
            raise Ablehnung("in_gebrauch", f"{a.name} hat offene Aufträge.")
        await self.b.ablage.anwendungen.loeschen(kennung)
        self.b.anwendung_entfernen(kennung)
        await self._pruefen(wer, "Anwendung entfernt", a.name)

    # ── Modellnamen ──────────────────────────────────────────────────────
    async def alias_setzen(self, alias: str, familie: str, wer: str) -> None:
        if not any(m.familie == familie for m in self.b.verbund.modelle.values()):
            raise Ablehnung("kein_modell", f"Modell {familie} ist im Verbund nicht bekannt.")
        await self.b.ablage.aliasse.speichern(AliasEintrag(alias=alias, familie=familie))
        self.b.aliasse[alias] = familie
        await self._pruefen(wer, f"Zweitname {alias} für {familie}")

    async def alias_loeschen(self, alias: str, wer: str) -> None:
        await self.b.ablage.aliasse.loeschen(alias)
        self.b.aliasse.pop(alias, None)
        await self._pruefen(wer, f"Zweitname {alias} entfernt")
