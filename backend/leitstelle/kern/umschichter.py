"""Umschichter: wertet die Regelgraphen aus, schützt vor Schleifen und führt Maßnahmen aus.

Schleifenschutz (ARCHITEKTUR 5.6):
- Hauptregler vor Regelwerk: bei Auslaufen und Halt wird nichts umgeschichtet.
- Flattern: dieselbe Bewegung (Laden oder Entladen einer Modellfamilie auf einem Knoten, Beenden eines Arbeiters des
  Läufers mit derselben Modelldatei) zum zweiten Mal innerhalb des Fensters sperrt die Beteiligten auf dem Knoten für
  die Ruhezeit und meldet es.
- Je Auftrag höchstens die eingestellte Zahl Umleitungen.
- Höchstens eine Maßnahme je Knoten und Takt, höchstens die eingestellte Zahl je Fenster.
- Gewinnschwelle und Mindestverweildauer stecken in den Bausteinen und im Speicherplaner.
- Automatik "vorschlagen" plant nur; "aus" wertet nicht aus.
"""

from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from .messungen import Messwerk
from .modelle import Massnahme, Verbund
from .regeln.auswerter import Lauf, Regelgraph, auswerten
from .werte import SZENARIEN_AB_WERK_AUS, Automatik, Betriebsmodus, Hintergrundstufe, Massnahmenart, Massnahmenzustand

#: Hauptrichtung einer Maßnahme nach ihrer ersten bewegenden Aktion; Partizip für die Meldung bei Flattern
RICHTUNGEN = {"modell_laden": "laden", "modell_entladen": "entladen", "auftrag_umleiten": "umleiten", "auftrag_extern": "umleiten",
              "instanz_starten": "laden", "laeufer_prozess_beenden": "beenden"}
GETAN = {"laden": "geladen", "entladen": "entladen", "beenden": "beendet"}
STUFENAKTIONEN = ("hintergrund_drosseln", "hintergrund_auf_knoten_anhalten", "hintergrund_auf_knoten_freigeben")


class Vollzug(Protocol):
    """Was die Leitstelle an der Außenwelt tun kann; der Schein-Verbund und die Adapter setzen es um."""

    def dienst_starten(self, dienst: str) -> None: ...
    def modell_laden(self, modell: str) -> None: ...
    def instanz_starten(self, dienst: str, familie: str, vorbild: str) -> None: ...
    def modell_entladen(self, modell: str) -> None: ...
    def auftrag_umleiten(self, auftrag: str, dienst: str, modell: str, knoten: str | None) -> None: ...
    def auftrag_extern(self, auftrag: str, dienst: str, modell: str) -> None: ...
    def melden(self, text: str) -> None: ...
    def signal(self, anwendung: str, art: str, nutzlast: dict) -> None: ...
    def laufende_abbrechen_mit_teilergebnis(self, knoten: str) -> None: ...
    def wartende_neu_einreihen(self, knoten: str) -> None: ...
    def bevorzugter_knoten(self, knoten: str | None) -> None: ...
    def hintergrund(self, an: bool) -> None: ...
    def laeufer_prozess_beenden(self, knoten: str, pid: int) -> None: ...
    def hintergrund_stufe(self, knoten: str, stufe: Hintergrundstufe, grund: str) -> None: ...


def zuruecknehmen(verbund: Verbund, art: Massnahmenart, vollzug: Vollzug) -> list[str]:
    """Was eine Regel als Zustand hinterlässt, nimmt die Leitstelle zurück, sobald sie nicht mehr wirkt (abgeschaltet oder
    Automatik nicht mehr selbst handelnd); sonst bliebe etwa ein gedrosselter Hintergrund gedrosselt, weil die Regel, die
    ihn freigäbe, nicht mehr läuft. Liefert die Sätze für den Verlauf."""
    saetze = []
    if art == Massnahmenart.HINTERGRUND_LAGE and not verbund.hintergrund_an:
        vollzug.hintergrund(True)
        saetze.append('Hintergrund läuft wieder: die Regel "Hintergrund bei Lage" wirkt nicht mehr')
    elif art == Massnahmenart.VERLAGERN and verbund.hintergrund_knoten_bevorzugt:
        vollzug.bevorzugter_knoten(None)
        saetze.append('Kein Rechner mehr bevorzugt für Hintergrund: die Regel "Verlagern" wirkt nicht mehr')
    elif art == Massnahmenart.HINTERGRUND_RECHNERLAST:
        for k in verbund.knoten.values():
            if k.hintergrund_stufe != Hintergrundstufe.FREI:
                vollzug.hintergrund_stufe(k.kennung, Hintergrundstufe.FREI, 'die Regel "Hintergrund bei Rechnerlast" wirkt nicht mehr')
                saetze.append(f'Hintergrund auf {k.name} freigegeben: die Regel "Hintergrund bei Rechnerlast" wirkt nicht mehr')
    return saetze


def _text_fuellen(vorlage: str, werte: dict, verbund: Verbund, lauf: Lauf) -> str:
    daten = dict(werte)
    if lauf.knoten_ziel and lauf.knoten_ziel in verbund.knoten:
        daten.setdefault("knoten", verbund.knoten[lauf.knoten_ziel].name)
    if lauf.modell_ziel and lauf.modell_ziel in verbund.modelle:
        daten.setdefault("modell", verbund.modelle[lauf.modell_ziel].name)
    if lauf.auftrag and lauf.auftrag in verbund.auftraege:
        daten.setdefault("anwendung", verbund.anwendungen[verbund.auftraege[lauf.auftrag].anwendung].name)
    try:
        return vorlage.format(**{k: v for k, v in daten.items() if isinstance(v, (str, int, float))})
    except (KeyError, IndexError):
        return vorlage


class Umschichter:
    def __init__(self, graphen: list[Regelgraph]) -> None:
        self.graphen = graphen
        self.verlauf: list[Massnahme] = []
        self.sperren: dict[str, float] = {}      # "familie@knoten" -> gesperrt bis
        self.bewegungen: list[tuple[float, str]] = []   # (zeit, "laden:familie@knoten")

    # ── Schleifenschutz ──────────────────────────────────────────────────
    def _schluessel(self, lauf: Lauf, modell: str | None, knoten: str | None, verbund: Verbund) -> str | None:
        if not modell or modell not in verbund.modelle:
            return None
        fam = verbund.modelle[modell].familie
        return f"{fam}@{knoten or verbund.dienste[verbund.modelle[modell].dienst].knoten}"

    def _gesperrt(self, schluessel: str | None, jetzt: float) -> bool:
        return bool(schluessel) and self.sperren.get(schluessel, -1.0) > jetzt

    def _flattert(self, bewegung: str, verbund: Verbund) -> bool:
        """Flattern heißt: dieselbe Bewegung (Laden oder Entladen derselben Familie auf demselben Knoten) käme zum zweiten
        Mal innerhalb des Fensters. Ein einzelnes Laden mit späterem Entladen ist eine gewöhnliche Umschichtung; erst der
        geschlossene Kreis (laden, entladen, wieder laden) ist Flattern. Ladevorgänge des Zuteilers zählen mit."""
        r = verbund.regelwerk
        for zeit, b in reversed(self.bewegungen):
            if verbund.zeit_s - zeit > r.fenster_s:
                break
            if b == bewegung:
                return True
        return False

    def merke_bewegung(self, richtung: str, familie: str, knoten: str | None, zeit_s: float) -> None:
        """Auch Ladevorgänge des Zuteilers zählen fürs Flattern."""
        self.bewegungen.append((zeit_s, f"{richtung}:{familie}@{knoten}"))

    def _ausduennen(self, verbund: Verbund) -> None:
        """Dauerbetrieb: nur behalten, was der Schleifenschutz noch braucht (Fenster, laufende Sperren)."""
        grenze = verbund.zeit_s - verbund.regelwerk.fenster_s
        self.verlauf = [m for m in self.verlauf if m.zeit_s >= grenze]
        self.bewegungen = [(z, b) for z, b in self.bewegungen if z >= grenze]
        self.sperren = {k: bis for k, bis in self.sperren.items() if bis > verbund.zeit_s}

    def _im_fenster(self, verbund: Verbund) -> int:
        r = verbund.regelwerk
        return sum(1 for m in self.verlauf if m.zustand == Massnahmenzustand.AUSGEFUEHRT and verbund.zeit_s - m.zeit_s <= r.fenster_s)

    # ── Takt ─────────────────────────────────────────────────────────────
    def takt(self, verbund: Verbund, messwerk: Messwerk, vollzug: Vollzug) -> list[Massnahme]:
        r = verbund.regelwerk
        if verbund.betriebsmodus != Betriebsmodus.NORMAL or r.automatik == Automatik.AUS:
            return []
        self._ausduennen(verbund)
        neu: list[Massnahme] = []
        knoten_belegt: set[str] = set()
        for graph in self.graphen:
            if not graph.aktiv or not r.szenarien_an.get(graph.art, graph.art not in SZENARIEN_AB_WERK_AUS):
                continue
            for lauf in auswerten(graph, verbund, messwerk):
                m = self._massnahme_aus_lauf(lauf, verbund)
                if not lauf.aktionen:
                    m.zustand = Massnahmenzustand.GEPRUEFT_OHNE_AKTION if any(s.ergebnis == "nein" for s in lauf.weg) else Massnahmenzustand.NICHT_AUSGELOEST
                    neu.append(m)
                    continue
                grund_sperre = self._sperrgrund(lauf, m, verbund, knoten_belegt)
                if grund_sperre:
                    m.zustand = Massnahmenzustand.GESPERRT
                    m.grund = grund_sperre
                    neu.append(m)
                    continue
                if r.automatik == Automatik.VORSCHLAGEN:
                    m.zustand = Massnahmenzustand.GEPLANT
                    neu.append(m)
                    continue
                self._ausfuehren(lauf, m, verbund, vollzug)
                m.zustand = Massnahmenzustand.AUSGEFUEHRT
                for b in m.bewegungen:
                    self.bewegungen.append((verbund.zeit_s, b))
                for kz in (lauf.knoten_ziel, lauf.knoten_quelle):
                    if kz:
                        knoten_belegt.add(kz)
                neu.append(m)
        self.verlauf.extend(x for x in neu if x.zustand in (Massnahmenzustand.AUSGEFUEHRT, Massnahmenzustand.GESPERRT, Massnahmenzustand.GEPLANT))
        verbund.massnahmen.extend(neu)
        return neu

    def _massnahme_aus_lauf(self, lauf: Lauf, verbund: Verbund) -> Massnahme:
        # Hauptrichtung: die erste Aktion des Laufs, die etwas bewegt (Leerlauf räumen = entladen, Umleiten = umleiten)
        richtung = next((RICHTUNGEN[a.baustein] for a in lauf.aktionen if a.baustein in RICHTUNGEN), None)
        fam = None
        if lauf.modell_ziel and lauf.modell_ziel in verbund.modelle:
            fam = verbund.modelle[lauf.modell_ziel].familie
        elif lauf.modelle_entladen:
            fam = verbund.modelle[lauf.modelle_entladen[0]].familie
        knoten = lauf.knoten_ziel or lauf.knoten_quelle
        bewegungen: list[str] = []
        for a in lauf.aktionen:
            if a.baustein == "modell_laden" and a.werte.get("modell") in verbund.modelle:
                mm = verbund.modelle[a.werte["modell"]]
                bewegungen.append(f"laden:{mm.familie}@{verbund.dienste[mm.dienst].knoten}")
            if a.baustein == "modell_entladen":
                for mk in a.werte.get("modelle", []):
                    mm = verbund.modelle[mk]
                    if mm.zusatz:
                        continue      # weitere Instanz: die Familie bleibt geladen, kein Hin und Her, das der Flatterschutz meint
                    bewegungen.append(f"entladen:{mm.familie}@{verbund.dienste[mm.dienst].knoten}")
            if a.baustein == "laeufer_prozess_beenden":
                bewegungen.append(f"beenden:{a.werte['pfad']}@{a.werte['knoten']}")      # voller Pfad: Dateinamen wiederholen sich
        meldung = next((a for a in lauf.aktionen if a.baustein == "melden"), None)
        grund = _text_fuellen(meldung.parameter.get("text", ""), lauf.werte, verbund, lauf) if meldung else (lauf.abschluss or "")
        return Massnahme(kennung=uuid4().hex, art=lauf.art, zustand=Massnahmenzustand.GEPLANT, regel=lauf.regel, zeit_s=verbund.zeit_s, grund=grund,
                         gewinn_s=lauf.gewinn_s, aufwand_s=lauf.aufwand_s, schritte=[f"{s.baustein}: {s.ergebnis}" for s in lauf.weg],
                         auftraege=[lauf.auftrag] if lauf.auftrag else [], knoten=knoten, modell=fam, richtung=richtung, bewegungen=bewegungen)

    def _sperrgrund(self, lauf: Lauf, m: Massnahme, verbund: Verbund, knoten_belegt: set[str]) -> str | None:
        r = verbund.regelwerk
        jetzt = verbund.zeit_s
        if self._im_fenster(verbund) >= r.max_massnahmen_je_fenster:
            return f"Höchstzahl von {r.max_massnahmen_je_fenster} Maßnahmen je {r.fenster_s:.0f} s erreicht"
        for kz in (lauf.knoten_ziel, lauf.knoten_quelle):
            if kz and kz in knoten_belegt:
                return f"auf {verbund.knoten[kz].name} läuft in diesem Takt schon eine Maßnahme"
        if lauf.auftrag and lauf.auftrag in verbund.auftraege and m.richtung == "umleiten":
            if verbund.auftraege[lauf.auftrag].umgeleitet >= r.max_umleitungen_je_auftrag:
                return "Auftrag wurde schon umgeleitet; kein zweites Mal"
        for b in m.bewegungen:
            schluessel = b.split(":", 1)[1]
            if self._gesperrt(schluessel, jetzt):
                return f"{schluessel} ist nach Flattern gesperrt bis {self.sperren[schluessel]:.0f} s"
        for b in m.bewegungen:
            if self._flattert(b, verbund):
                for bb in m.bewegungen:
                    self.sperren[bb.split(":", 1)[1]] = jetzt + r.ruhezeit_s
                richtung, schluessel = b.split(":", 1)
                return f"Flattern erkannt: {schluessel} würde innerhalb von {r.fenster_s:.0f} s zum zweiten Mal {GETAN[richtung]}; gesperrt für {r.ruhezeit_s:.0f} s"
        return None

    def _ausfuehren(self, lauf: Lauf, m: Massnahme, verbund: Verbund, vollzug: Vollzug) -> None:
        for a in lauf.aktionen:
            w = a.werte
            match a.baustein:
                case "dienst_starten":
                    vollzug.dienst_starten(w["dienst"])
                case "modell_laden":
                    vollzug.modell_laden(w["modell"])
                case "instanz_starten":
                    for _ in range(w["anzahl"]):
                        vollzug.instanz_starten(w["dienst"], w["familie"], w["vorbild"])
                case "modell_entladen":
                    for mk in w["modelle"]:
                        vollzug.modell_entladen(mk)
                case "auftrag_umleiten":
                    vollzug.auftrag_umleiten(w["auftrag"], w["dienst"], w["modell"], w["knoten"])
                case "auftrag_extern":
                    vollzug.auftrag_extern(w["auftrag"], w["dienst"], w["modell"])
                case "melden":
                    vollzug.melden(m.grund)
                case "signal_senden":
                    vollzug.signal(w["anwendung"], w["art"], {"auftrag": lauf.auftrag})
                case "laufende_abbrechen_mit_teilergebnis":
                    vollzug.laufende_abbrechen_mit_teilergebnis(w["knoten"])
                case "wartende_neu_einreihen":
                    vollzug.wartende_neu_einreihen(w["knoten"])
                case "bevorzugten_knoten_setzen":
                    vollzug.bevorzugter_knoten(w["knoten"])
                case "hintergrund_anhalten" | "hintergrund_fortsetzen":
                    vollzug.hintergrund(w["an"])
                case "laeufer_prozess_beenden":
                    vollzug.laeufer_prozess_beenden(w["knoten"], w["pid"])
                case baustein if baustein in STUFENAKTIONEN:
                    vollzug.hintergrund_stufe(w["knoten"], Hintergrundstufe(w["stufe"]), w["grund"])
