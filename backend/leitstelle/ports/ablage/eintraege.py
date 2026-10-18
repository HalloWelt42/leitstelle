"""Datensätze der Ablage: was dauerhaft gespeichert wird. Pydantic, nie rohe Dicts.

Der Laufzustand (geladene Modelle, offene Aufträge) lebt im Verbund des Kerns; hier steht, was einen
Neustart überdauern muss: eingerichtete Anschlussstellen, Anwendungen, Verlauf, Messungen, Regelwerk.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ...kern.werte import Auftragszustand, Betriebsmodus, Faehigkeit, Prioritaet, Zone


class Adapterart(str, Enum):
    """Wie die Leitstelle mit einem Dienst spricht. Neue Arten kommen mit neuen Adaptern dazu."""

    OPENAI_KOMPATIBEL = "openai_kompatibel"
    AGENT = "agent"                     # Prozessdienste eines Knoten-Agenten; Starten ist Laden


class KnotenEintrag(BaseModel):
    kennung: str
    name: str
    adresse: str                       # Rechnername oder IP im Netz
    zone: Zone = Zone.HEIM
    speicher_gb: float
    system_gb: float = 6.0
    budget_fest_gb: float | None = None
    hintergrund_von: int | None = None  # Stunde, ab der Hintergrundarbeit bevorzugt hierher darf
    hintergrund_bis: int | None = None
    agent_fingerabdruck: str | None = None   # Schlüssel des Knoten-Agenten (nur Fingerabdruck zum Erkennen)
    agent_geheim: str | None = None          # derselbe Schlüssel verschlüsselt, zum Aufdecken


class DienstEintrag(BaseModel):
    kennung: str
    name: str
    art: Adapterart = Adapterart.OPENAI_KOMPATIBEL
    adresse: str                       # Basisadresse, zum Beispiel http://mac-studio.local:1234
    knoten: str | None = None          # None heißt externer Anbieter
    extern: bool = False
    zugang_geheim: str | None = None   # verschlüsselt im Tresor; nur wenn die Gegenstelle einen verlangt
    plaetze: int = 4                   # gleichzeitige Aufträge je geladenem Modell


class AnwendungEintrag(BaseModel):
    kennung: str
    name: str
    schluessel_fingerabdruck: str
    schluessel_geheim: str
    prioritaet: Prioritaet = Prioritaet.NORMAL
    faehigkeiten: set[Faehigkeit] = Field(default_factory=lambda: {Faehigkeit.TEXT, Faehigkeit.EINBETTUNG, Faehigkeit.UEBERSETZEN, Faehigkeit.BILD_BESCHREIBEN, Faehigkeit.WERKZEUG})
    zonen: set[Zone] = Field(default_factory=lambda: {Zone.HEIM})
    extern_erlaubt: bool = False
    gleichzeitig: int = 4
    ketten: dict[Faehigkeit, list[str]] = Field(default_factory=dict)
    gesperrt: bool = False
    sperrgrund: str = ""
    angelegt_s: float = 0.0


class AliasEintrag(BaseModel):
    """Zusätzlicher Name für eine Modellfamilie, zum Beispiel die alte Schreibweise einer Anwendung."""

    alias: str
    familie: str


class Schritt(BaseModel):
    """Ein Eintrag der Zeitleiste eines Auftrags: Zustand und Begründung, wie die Leitstelle sie sah."""

    zeit_s: float
    zustand: Auftragszustand
    text: str = ""


class AuftragEintrag(BaseModel):
    kennung: str
    anwendung: str
    faehigkeit: Faehigkeit
    prioritaet: Prioritaet
    titel: str = ""
    zustand: Auftragszustand
    grund: str | None = None           # Wort aus PROTOKOLL.md Abschnitt 7, wenn nicht fertig
    begruendung: str = ""
    festes_modell: str | None = None
    familie: str | None = None
    modell_name: str | None = None
    dienst: str | None = None
    knoten: str | None = None
    extern: bool = False
    umgeleitet: int = 0
    eingang_s: float
    start_s: float | None = None
    ende_s: float | None = None
    erstes_stueck_s: float | None = None
    token_ein: int | None = None
    token_aus: int | None = None
    teilergebnis_zeichen: int = 0
    weg: str = "fassade"
    schritte: list[Schritt] = Field(default_factory=list)
    arbeit: str | None = None          # Arbeit der Anwendung (Kopf X-Leitstelle-Arbeit), "anwendung:kennung"


class Kennzahlen(BaseModel):
    """Abgeschlossene Aufträge in einem Zeitraum (Übersicht: heute)."""

    ab_s: float
    fertig: int = 0
    fehler: int = 0
    abgebrochen: int = 0
    abgelehnt: int = 0
    wartezeit_mittel_s: float | None = None
    erstes_stueck_mittel_s: float | None = None


class BetriebEinstellung(BaseModel):
    """Stellung des Hauptreglers; überdauert einen Neustart."""

    modus: Betriebsmodus = Betriebsmodus.NORMAL
    hintergrund_an: bool = True


class PruefEintrag(BaseModel):
    zeit_s: float
    wer: str
    was: str
    gegenstand: str = ""


class Richtung(str, Enum):
    LADEN = "laden"
    ENTLADEN = "entladen"


class Ausgang(str, Enum):
    OK = "ok"
    ABGELEHNT = "abgelehnt"           # der Dienst hat das Laden abgelehnt (etwa zu wenig Speicher)
    GESCHEITERT = "gescheitert"       # Fehler beim Entladen; der nächste Abgleich zeigt den wahren Stand


class Bewegung(BaseModel):
    """Ein Laden oder Entladen als Rohdatum, damit sich Fristen und Regeln aus dem Verlauf einstellen lassen
    (ZUSAMMENSPIEL Z2). `zeit_s` ist der Beginn beim Dienst, `dauer_s` bis zur Antwort."""

    zeit_s: float
    richtung: Richtung
    familie: str
    name: str
    knoten: str | None = None
    gb: float
    dauer_s: float
    ausgang: Ausgang = Ausgang.OK
    meldung: str = ""
