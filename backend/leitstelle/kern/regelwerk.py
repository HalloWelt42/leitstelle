"""Regelwerk: alles Einstellbare der Selbststeuerung an einem Ort, jeder Wert mit seiner Bedeutung.

Je Wert steht hier, wie er heißt, was er bewirkt, in welcher Einheit er zählt, zu welcher Gruppe er gehört und in welchen
Grenzen ein Mensch ihn einstellen darf (`Regelwert`). Je Maßnahme der Selbststeuerung steht hier ihre Erklärung und ihre
Gruppe (`SZENARIEN`). Oberfläche, Schnittstelle und Prüfprotokoll lesen beides von hier; die Grenzen gelten für
Änderungen von Hand, Tests dürfen außerhalb rechnen (etwa mit einem Takt von 0,2 s).

Gespeichert wird nur, was von der Vorgabe ab Werk abweicht (`abweichungen`); ein unverändert gelassener Wert folgt so
einer neuen Vorgabe einer späteren Fassung.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

from .werte import SZENARIEN_AB_WERK_AUS, WORT, Automatik, Faehigkeit, Massnahmenart, Prioritaet


class Einheit(str, Enum):
    SEKUNDEN = "sekunden"
    GB = "gb"
    MILLIARDEN = "milliarden"         # Parameter eines Modells
    PROZENT = "prozent"               # Prozent aller Kerne
    PUNKTE = "punkte"                 # Prozentpunkte (Abstand zweier Prozentwerte)
    PROZENT_KERN = "prozent_kern"     # Prozent eines Kerns: 100 ist ein ganzer Kern
    ANTEIL = "anteil"                 # 0 bis 1, gezeigt als Prozent
    ANZAHL = "anzahl"
    FAKTOR = "faktor"
    SCHALTER = "schalter"             # an oder aus
    WAHL = "wahl"                     # einer aus mehreren Werten
    MEHRFACH = "mehrfach"             # beliebig viele aus mehreren Werten (Liste)


class Regelgruppe(str, Enum):
    SELBSTSTEUERUNG = "selbststeuerung"
    SPEICHER = "speicher"
    AUSWEICHEN = "ausweichen"
    HINTERGRUND = "hintergrund"
    RUHE = "ruhe"
    EINBETTUNG = "einbettung"
    LAST = "last"


@dataclass(frozen=True)
class Gruppe:
    titel: str
    erklaerung: str


GRUPPEN: dict[Regelgruppe, Gruppe] = {
    Regelgruppe.SELBSTSTEUERUNG: Gruppe("Selbststeuerung", "Wie weit die Leitstelle von selbst eingreift und wie sie sich vor Hin und Her schützt."),
    Regelgruppe.SPEICHER: Gruppe("Speicher und Laden", "Wann Modelle laden, weichen oder bleiben; begonnene Arbeit behält ihre Modelle."),
    Regelgruppe.AUSWEICHEN: Gruppe("Kette und Ausweichen", "Wohin ein wartender Auftrag ausweicht: andere Modelle seiner Kette, andere "
                                                           "Rechner oder ein externer Anbieter, den die Anwendung erlaubt."),
    Regelgruppe.HINTERGRUND: Gruppe("Hintergrund", "Wann Hintergrundarbeit wartet und wohin sie bevorzugt geht."),
    Regelgruppe.RUHE: Gruppe("Nur bei Ruhe", "Arbeit der niedrigsten Stufe: sie bekommt nur ein Modell, wenn keine andere Arbeit läuft "
                                             "oder wartet, und gibt nach, sobald etwas anderes kommt; der laufende Auftrag rechnet zu Ende, "
                                             "die übrigen warten auf die nächste Ruhe."),
    Regelgruppe.EINBETTUNG: Gruppe("Einbettung", "Weitere Instanzen eines Einbettungsmodells bei Andrang und ihr Rückbau."),
    Regelgruppe.LAST: Gruppe("Läufer und Last", "Arbeiter des Modell-Läufers ohne Auftrag und Hintergrund bei Last des Menschen am Rechner."),
}


@dataclass(frozen=True)
class Regelwert:
    """Bedeutung eines einstellbaren Werts für Menschen und die Grenzen für Änderungen von Hand."""

    titel: str
    erklaerung: str
    einheit: Einheit
    gruppe: Regelgruppe
    min: float | None = None
    max: float | None = None
    schritt: float | None = None
    szenario: Massnahmenart | None = None   # gehört zu dieser Maßnahme; None: gilt für mehrere
    wahl: tuple[tuple[Any, str], ...] = ()  # bei Wahl und Mehrfach: die möglichen Werte (wie im JSON) mit Wort


@dataclass(frozen=True)
class Szenario:
    """Eine Maßnahme der Selbststeuerung zum Ein- und Ausschalten (der Name steht in WORT)."""

    gruppe: Regelgruppe
    erklaerung: str


SZENARIEN: dict[Massnahmenart, Szenario] = {
    Massnahmenart.UMLEITEN: Szenario(Regelgruppe.SPEICHER, "Wartet ein Auftrag auf Speicher und hat ein anderer Rechner Platz für sein Modell, "
                                                           "lädt die Leitstelle es dort und leitet den Auftrag um, wenn das mehr Wartezeit spart, als es "
                                                           "kostet (Gewinnfaktor)."),
    Massnahmenart.LEERLAUF_RAEUMEN: Szenario(Regelgruppe.SPEICHER, "Wartet ein Auftrag auf Speicher, entlädt die Leitstelle ein Modell, das seit der "
                                                                   "Bedarfsfrist keinen Auftrag hatte, und lädt das gebrauchte; nie ein geschütztes, "
                                                                   "rechnendes oder von begonnener Arbeit gehaltenes."),
    Massnahmenart.VORWAERMEN: Szenario(Regelgruppe.SPEICHER, "Steht ein Auftrag für ein Modell an, das noch nicht geladen ist, und passt es ohne "
                                                             "Entladen, lädt die Leitstelle es schon vorher."),
    Massnahmenart.DOPPEL_AUFLOESEN: Szenario(Regelgruppe.SPEICHER, "Ist ein Modell auf zwei Rechnern geladen, eine Kopie ungenutzt und anderswo "
                                                                   "Bedarf, entlädt die Leitstelle die ungenutzte."),
    Massnahmenart.WEITERE_INSTANZ: Szenario(Regelgruppe.SPEICHER, "Wartet ein Auftrag auf einen Platz eines Dienstes im Maschinenraum, startet die "
                                                                  "Leitstelle eine weitere Instanz, wenn sie ohne Entladen passt und sich lohnt."),
    Massnahmenart.KETTE_AUSWEICHEN: Szenario(Regelgruppe.AUSWEICHEN, "Wartet ein Auftrag und ist ein anderes Modell seiner Kette geladen und frei, "
                                                                     "rechnet er dort."),
    Massnahmenart.EXTERN_AUSWEICHEN: Szenario(Regelgruppe.AUSWEICHEN, "Würde ein Auftrag länger als die Schwelle warten und erlaubt die Anwendung ein "
                                                                      "externes Modell (Zone extern und ihre Erlaubnisliste), rechnet er beim Anbieter."),
    Massnahmenart.UMVERTEILEN: Szenario(Regelgruppe.AUSWEICHEN, "Wird ein Rechner mit offenen Aufträgen unerreichbar, enden laufende mit "
                                                                "Teilergebnis, wartende kommen neu in die Warteschlange."),
    Massnahmenart.HINTERGRUND_LAGE: Szenario(Regelgruppe.HINTERGRUND, "Ist die Lage angespannt oder im Engpass, wartet Hintergrundarbeit; bei "
                                                                      "ruhiger Lage läuft sie weiter. Aus: Hintergrund läuft auch bei angespannter Lage."),
    Massnahmenart.VERLAGERN: Szenario(Regelgruppe.HINTERGRUND, "Beginnt das Zeitfenster eines Rechners (Knoten, Hintergrund ab Stunde), geht "
                                                               "Hintergrundarbeit bevorzugt dorthin."),
    Massnahmenart.EINBETTUNG_VERSTAERKEN: Szenario(Regelgruppe.EINBETTUNG, "Warten Einbettungen länger als der Andrang, lädt die Leitstelle weitere "
                                                                           "Instanzen des Einbettungsmodells, bis zur Höchstzahl des Dienstes und mit "
                                                                           "Spielraum im Budget."),
    Massnahmenart.EINBETTUNG_ZURUECKBAUEN: Szenario(Regelgruppe.EINBETTUNG, "Weitere Einbettungsinstanzen, die die Ruhezeit nichts zu tun hatten, "
                                                                            "entlädt die Leitstelle; die Grundinstanz bleibt."),
    Massnahmenart.LAEUFER_OHNE_AUFTRAG: Szenario(Regelgruppe.LAST, "Rechnet ein Arbeiter des Modell-Läufers seit der Frist über der Schwelle, ohne "
                                                                   "dass die Leitstelle dort etwas rechnen lässt, beendet ihn der Maschinenraum; hängt ein "
                                                                   "Programm am Leitstand vorbei am Läufer, nur melden. Aus: nur melden, beenden von Hand."),
    Massnahmenart.HINTERGRUND_RECHNERLAST: Szenario(Regelgruppe.LAST, "Braucht der Mensch den Rechner (Fremdlast im Mittel) oder ist sein "
                                                                      "Docker-Rechner ausgelastet (Docker-Last im Mittel, ohne die Container von "
                                                                      "Anwendungen mit Hintergrundarbeit), drosselt oder hält die Leitstelle dort "
                                                                      "Hintergrundarbeit an; es gilt das höhere der beiden Maße. Normale Aufträge "
                                                                      "bleiben unberührt."),
}

#: Wörter der Automatik (WAHL)
AUTOMATIK_WORT = {Automatik.AUS: "Aus", Automatik.VORSCHLAGEN: "Vorschlagen", Automatik.SELBST: "Selbst handeln"}
#: Wörter der Prioritäten (WAHL "nur bei Ruhe bis")
PRIORITAET_WORT = {Prioritaet.HINTERGRUND: "Hintergrund", Prioritaet.NORMAL: "Normal", Prioritaet.HOCH: "Hoch", Prioritaet.DRINGEND: "Dringend"}

R = Regelgruppe
E = Einheit


class Regelwerk(BaseModel):
    """Alle Werte der Selbststeuerung; Bedeutung und Grenzen je Wert im `Regelwert` daneben."""

    automatik: Annotated[Automatik, Regelwert(
        "Automatik", "Aus: keine Regel greift. Vorschlagen: Maßnahmen erscheinen als Vorschlag in der Übersicht, nichts geschieht. "
        "Selbst handeln: die Leitstelle führt sie aus und meldet sie mit Grund.", E.WAHL, R.SELBSTSTEUERUNG,
        wahl=tuple((a.value, w) for a, w in AUTOMATIK_WORT.items()))] = Automatik.SELBST
    gewinnfaktor: Annotated[float, Regelwert(
        "Gewinnfaktor", "Eine Maßnahme, die lädt oder umleitet, muss so viel mal mehr Wartezeit sparen, als sie selbst kostet (Ladezeit gemessen).",
        E.FAKTOR, R.SELBSTSTEUERUNG, 0.5, 10, 0.1)] = 2.0
    max_massnahmen_je_fenster: Annotated[int, Regelwert(
        "Höchstens Maßnahmen je Fenster", "Mehr Maßnahmen führt die Leitstelle im Fenster nicht aus; weitere werden gesperrt gemeldet.",
        E.ANZAHL, R.SELBSTSTEUERUNG, 1, 100, 1)] = 6
    fenster_s: Annotated[float, Regelwert(
        "Fenster", "Zeitraum für die Höchstzahl der Maßnahmen und für das Erkennen von Flattern (dieselbe Bewegung zweimal).",
        E.SEKUNDEN, R.SELBSTSTEUERUNG, 60, 86400, 60)] = 600.0
    ruhezeit_s: Annotated[float, Regelwert(
        "Ruhezeit nach Flattern", "So lange sind Modell und Rechner nach erkanntem Flattern für weitere Maßnahmen gesperrt.",
        E.SEKUNDEN, R.SELBSTSTEUERUNG, 60, 86400, 60)] = 1800.0
    max_umleitungen_je_auftrag: Annotated[int, Regelwert(
        "Umleitungen je Auftrag", "So oft darf ein Auftrag höchstens umgeleitet werden.", E.ANZAHL, R.SELBSTSTEUERUNG, 0, 10, 1)] = 1
    umschichter_takt_s: Annotated[float, Regelwert(
        "Takt der Regeln", "So oft prüft die Leitstelle alle Regeln; zugeteilt wird unabhängig davon sofort.",
        E.SEKUNDEN, R.SELBSTSTEUERUNG, 1, 300, 1)] = 5.0

    budget_reserve_gb: Annotated[float, Regelwert(
        "Reserve", "So viel Speicher eines Rechners bleibt für System und Programme; der Rest ist das Budget der Modelle (außer bei festem "
        "Budget des Rechners).", E.GB, R.SPEICHER, 0, 512, 0.5)] = 18.0
    schutzgrenze_mrd: Annotated[float, Regelwert(
        "Schutzgrenze", "Modelle mit weniger Parametern entlädt die Leitstelle nie von selbst: sie bringen kaum Platz und sind schnell wieder "
        "gebraucht.", E.MILLIARDEN, R.SPEICHER, 0, 1000, 1)] = 10.0
    mindestverweildauer_s: Annotated[float, Regelwert(
        "Mindestverweildauer", "So lange bleibt ein Modell nach dem Laden mindestens, damit es kein Hin und Her gibt.",
        E.SEKUNDEN, R.SPEICHER, 0, 86400, 60)] = 600.0
    bedarfsfrist_s: Annotated[float, Regelwert(
        "Bedarfsfrist", "Wartet ein Auftrag auf Platz, darf ein Modell weichen, das so lange keinen Auftrag hatte.",
        E.SEKUNDEN, R.SPEICHER, 0, 86400, 10)] = 60.0
    leerlauf_s: Annotated[float, Regelwert(
        "Leerlauf ab", "Ab dieser Zeit ohne Auftrag gilt ein Modell als Leerlauf (Freigeben von Hand, Doppel auflösen).",
        E.SEKUNDEN, R.SPEICHER, 60, 604800, 60)] = 1800.0
    arbeit_frist_s: Annotated[float, Regelwert(
        "Frist begonnener Arbeit", "So lange nach ihrer letzten Nutzung hält eine begonnene Arbeit einer Anwendung ihre Modelle; für andere "
        "weichen sie nicht.", E.SEKUNDEN, R.SPEICHER, 0, 86400, 30)] = 300.0
    arbeit_ab_anfragen: Annotated[int, Regelwert(
        "Arbeit begonnen ab", "Ab so vielen Anfragen derselben Arbeit gilt sie als begonnen; eine einzelne Anfrage hält nichts.",
        E.ANZAHL, R.SPEICHER, 1, 100, 1)] = 2
    speicher_warnschwelle: Annotated[float, Regelwert(
        "Speicher knapp ab", "Ab diesem Anteil belegt heißt die Lage eines Rechners mit wartendem Auftrag angespannt.",
        E.ANTEIL, R.SPEICHER, 0.5, 1, 0.01)] = 0.92

    geladene_zuerst: Annotated[bool, Regelwert(
        "Geladene zuerst", "An: über die ganze Kette zuerst ein geladenes Modell mit freiem Platz, bevor etwas geladen wird. Aus: nur das erste "
        "Modell der Kette, sonst laden.", E.SCHALTER, R.AUSWEICHEN)] = True
    extern_schwelle_s: Annotated[float, Regelwert(
        "Extern ab Wartezeit", "Ab dieser erwarteten Wartezeit weicht ein Auftrag zu einem externen Modell aus, das seine Anwendung erlaubt.",
        E.SEKUNDEN, R.AUSWEICHEN, 0, 86400, 10, szenario=Massnahmenart.EXTERN_AUSWEICHEN)] = 120.0

    hintergrund_spaetestens_s: Annotated[float, Regelwert(
        "Hintergrund spätestens nach", "Nach dieser Wartezeit rückt ein Hintergrundauftrag auf Normal, damit nichts verhungert (nicht bei "
        "Hintergrund angehalten wegen Rechnerlast, nicht für Arbeit nur bei Ruhe).", E.SEKUNDEN, R.HINTERGRUND, 60, 86400, 60)] = 900.0

    ruhe_faehigkeiten: Annotated[list[Faehigkeit], Regelwert(
        "Fähigkeiten nur bei Ruhe", "Aufträge dieser Fähigkeiten (bis zur Priorität unten) sind Arbeit der niedrigsten Stufe: zugeteilt "
        "nur, wenn keine andere Arbeit läuft oder wartet. Keine: alles wie bisher.", E.MEHRFACH, R.RUHE,
        wahl=tuple((f.value, WORT[f.value]) for f in Faehigkeit))] = Field(default_factory=lambda: [Faehigkeit.EINBETTUNG])
    ruhe_bis_prioritaet: Annotated[Prioritaet, Regelwert(
        "Nur bei Ruhe bis Priorität", "Aufträge dieser Fähigkeiten bis zu dieser Priorität (wie die Anwendung sie schickt) warten auf "
        "Ruhe; höhere laufen wie gewohnt. Hintergrund: Masseneinbettung wartet, Suchen und Fragen einer App nicht.", E.WAHL, R.RUHE,
        wahl=tuple((p.value, w) for p, w in PRIORITAET_WORT.items()))] = Prioritaet.HINTERGRUND
    ruhe_ab_s: Annotated[float, Regelwert(
        "Ruhe ab", "So lange nach dem Ende der letzten anderen Arbeit gilt es als ruhig; erst dann bekommt Arbeit nur bei Ruhe wieder "
        "ein Modell. Überbrückt die Pausen zwischen den Schritten einer Arbeit.", E.SEKUNDEN, R.RUHE, 0, 86400, 10)] = 60.0

    einbettung_andrang_s: Annotated[float, Regelwert(
        "Andrang ab", "Warten Einbettungen so lange auf eine Instanz, lädt die Leitstelle weitere.", E.SEKUNDEN, R.EINBETTUNG, 1, 3600, 1, szenario=Massnahmenart.EINBETTUNG_VERSTAERKEN)] = 10.0
    einbettung_schonfrist_s: Annotated[float, Regelwert(
        "Schonfrist", "Ein Modell, das in dieser Zeit genutzt wurde, weicht nie für weitere Einbettungsinstanzen.",
        E.SEKUNDEN, R.EINBETTUNG, 0, 86400, 60, szenario=Massnahmenart.EINBETTUNG_VERSTAERKEN)] = 1800.0
    einbettung_ruhe_s: Annotated[float, Regelwert(
        "Rückbau nach Ruhe", "Weitere Instanzen, die so lange nichts zu tun hatten, entlädt die Leitstelle.", E.SEKUNDEN, R.EINBETTUNG, 10, 86400, 10, szenario=Massnahmenart.EINBETTUNG_ZURUECKBAUEN)] = 300.0

    laeufer_schwelle_prozent: Annotated[float, Regelwert(
        "Schwelle", "So viel muss ein Arbeiter des Läufers in jeder Messung rechnen, damit er als rechnend zählt (100 % ist ein ganzer Kern).",
        E.PROZENT_KERN, R.LAST, 5, 2000, 5, szenario=Massnahmenart.LAEUFER_OHNE_AUFTRAG)] = 50.0
    laeufer_frist_s: Annotated[float, Regelwert(
        "Frist", "So lange über der Schwelle, ohne dass in dieser Zeit ein Auftrag der Leitstelle auf dem Läufer lief, zugeteilt war oder "
        "geladen wurde: dann heißt es \"arbeitet ohne Auftrag\".", E.SEKUNDEN, R.LAST, 30, 86400, 30, szenario=Massnahmenart.LAEUFER_OHNE_AUFTRAG)] = 300.0
    last_frist_s: Annotated[float, Regelwert(
        "Mittel über", "Fremdlast und Docker-Last zählen im gleitenden Mittel über diese Zeit; kurze Spitzen schalten nichts.",
        E.SEKUNDEN, R.LAST, 15, 3600, 15, szenario=Massnahmenart.HINTERGRUND_RECHNERLAST)] = 60.0
    last_drosseln_ab_prozent: Annotated[float, Regelwert(
        "Fremdlast drosseln ab", "Ab dieser Fremdlast bekommt Hintergrund auf dem Rechner nur die Grundinstanz einer Familie; weitere Instanzen ohne Auftrag "
        "weichen sofort.", E.PROZENT, R.LAST, 1, 100, 1, szenario=Massnahmenart.HINTERGRUND_RECHNERLAST)] = 50.0
    last_anhalten_ab_prozent: Annotated[float, Regelwert(
        "Fremdlast anhalten ab", "Ab dieser Fremdlast wird Hintergrund auf dem Rechner nicht mehr zugeteilt, auch nicht nach der Fairness-Frist; laufende "
        "Aufträge rechnen zu Ende.", E.PROZENT, R.LAST, 1, 100, 1, szenario=Massnahmenart.HINTERGRUND_RECHNERLAST)] = 75.0
    last_abstand_prozent: Annotated[float, Regelwert(
        "Zurück erst", "Eine Stufe gilt, bis Fremdlast und Docker-Last um so viele Punkte unter ihre Grenzen fallen; so springt sie nicht bei "
        "jeder Schwankung.", E.PUNKTE, R.LAST, 0, 50, 1, szenario=Massnahmenart.HINTERGRUND_RECHNERLAST)] = 10.0
    docker_drosseln_ab_prozent: Annotated[float, Regelwert(
        "Docker-Last drosseln ab", "Ab dieser Docker-Last (Container ohne die von Anwendungen mit Hintergrundarbeit, Anteil aller Kerne des "
        "Docker-Rechners) wird Hintergrund auf dem Rechner gedrosselt wie bei der Fremdlast.", E.PROZENT, R.LAST, 1, 100, 1,
        szenario=Massnahmenart.HINTERGRUND_RECHNERLAST)] = 70.0
    docker_anhalten_ab_prozent: Annotated[float, Regelwert(
        "Docker-Last anhalten ab", "Ab dieser Docker-Last wird Hintergrund auf dem Rechner nicht mehr zugeteilt, wie bei der Fremdlast; laufende "
        "Aufträge rechnen zu Ende.", E.PROZENT, R.LAST, 1, 100, 1, szenario=Massnahmenart.HINTERGRUND_RECHNERLAST)] = 90.0

    @field_validator("ruhe_faehigkeiten")
    @classmethod
    def _ruhe_geordnet(cls, werte: list[Faehigkeit]) -> list[Faehigkeit]:
        """Jede Fähigkeit einmal, in der Reihenfolge der Aufzählung: so ist die Liste ein Wert wie jeder andere (Vergleich mit
        der Vorgabe, Prüfprotokoll)."""
        return [f for f in Faehigkeit if f in set(werte)]

    szenarien_an: dict[Massnahmenart, bool] = Field(default_factory=lambda: {a: a not in SZENARIEN_AB_WERK_AUS for a in Massnahmenart})

    @field_validator("szenarien_an")
    @classmethod
    def _alle_szenarien(cls, werte: dict[Massnahmenart, bool]) -> dict[Massnahmenart, bool]:
        """Ein gespeichertes Regelwerk aus einer älteren Fassung kennt neue Szenarien nicht: sie bekommen ihre Vorgabe ab
        Werk (sonst wäre etwa "Läufer ohne Auftrag" stillschweigend an)."""
        return {a: werte.get(a, a not in SZENARIEN_AB_WERK_AUS) for a in Massnahmenart}

    def abweichungen(self) -> dict[str, Any]:
        """Was von der Vorgabe ab Werk abweicht, als JSON; bei den Szenarien nur die abweichenden."""
        vorgabe = Regelwerk()
        aus: dict[str, Any] = {f: w for f, w in self.model_dump(mode="json", exclude={"szenarien_an"}).items() if w != getattr(vorgabe, f)}
        szenarien = {a.value: an for a, an in self.szenarien_an.items() if an != vorgabe.szenarien_an[a]}
        if szenarien:
            aus["szenarien_an"] = szenarien
        return aus

    def wirksam(self, art: Massnahmenart) -> bool:
        """Greift diese Maßnahme gerade von selbst (Automatik selbst handeln und Schalter an)?"""
        return self.automatik == Automatik.SELBST and self.szenarien_an.get(art, art not in SZENARIEN_AB_WERK_AUS)


def regelwert(feld: str) -> Regelwert:
    """Die Bedeutung eines Werts des Regelwerks."""
    return next(m for m in Regelwerk.model_fields[feld].metadata if isinstance(m, Regelwert))


def einstellbar() -> list[str]:
    """Alle Werte mit Bedeutung, in der Reihenfolge des Regelwerks (die Szenarien schalten getrennt)."""
    return [f for f, info in Regelwerk.model_fields.items() if any(isinstance(m, Regelwert) for m in info.metadata)]
