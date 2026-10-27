"""Datensätze der Ablage: was dauerhaft gespeichert wird. Pydantic, nie rohe Dicts.

Der Laufzustand (geladene Modelle, offene Aufträge) lebt im Verbund des Kerns; hier steht, was einen
Neustart überdauern muss: eingerichtete Anschlussstellen, Anwendungen, Verlauf, Messungen, Regelwerk.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from ...kern.werte import Auftragszustand, Betriebsmodus, Eignung, Faehigkeit, Prioritaet, Zone


class Adapterart(str, Enum):
    """Wie die Leitstelle mit einem Dienst spricht. Neue Arten kommen mit neuen Adaptern dazu."""

    OPENAI_KOMPATIBEL = "openai_kompatibel"
    EXTERN_OPENAI = "extern_openai"     # externer Anbieter im OpenAI-Format: nur Modellliste, Grenze je Minute
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
    adresse: str                       # Basisadresse, zum Beispiel http://macbook.local:1234
    knoten: str | None = None          # None heißt externer Anbieter
    extern: bool = False
    zugang_geheim: str | None = None   # verschlüsselt im Tresor; nur wenn die Gegenstelle einen verlangt
    plaetze: int = 4                   # gleichzeitige Aufträge je geladenem Modell
    anfragen_je_minute: int | None = None   # Grenzen des Anbieters je Minute, gleitend je Schlüssel (Hetzner 10 Anfragen,
    token_ein_je_minute: int | None = None  # 4 Mio. Token hinein, 100.000 heraus); die Leitstelle hält sie ein
    token_aus_je_minute: int | None = None
    abgleich_s: float | None = None    # Abstand der Zustandsabfrage, wenn der Dienst gesund ist (None: Vorgabe der Konfig)
    einbettung_instanzen: int = 1      # Modell-Läufer: so viele Instanzen je Einbettungsmodell bei Andrang (1: keine weiteren)
    einbettung_spielraum_gb: float = 4.0   # so viel bleibt im Budget des Rechners frei, wenn weitere Einbettungsinstanzen laden
                                       # (die Adresse bleibt stehen: aus heißt sofort wieder direkt)


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
    docker_projekte: list[str] = Field(default_factory=list)   # ihre Container im Docker-Rechner: Compose-Projekte oder Containernamen
    gesperrt: bool = False
    sperrgrund: str = ""
    angelegt_s: float = 0.0


class SteckbriefEintrag(BaseModel):
    """Von Hand eingetragen, was ein Dienst nicht selbst über ein Modell sagt (PROTOKOLL 4.8); gilt je Modellfamilie
    und geht der Auskunft des Dienstes vor. Leere Felder lassen die Auskunft des Dienstes stehen."""

    familie: str
    zweck: str = Field(default="", max_length=300)
    eignung: list[Eignung] = Field(default_factory=list)
    sprachen: list[str] = Field(default_factory=list)
    parameter_aktiv_mrd: float | None = Field(default=None, gt=0, le=10000)   # Mischmodelle, deren Name es nicht sagt

    @field_validator("sprachen")
    @classmethod
    def _sprachkuerzel(cls, werte: list[str]) -> list[str]:
        falsch = [w for w in werte if not (len(w) == 2 and w.isascii() and w.isalpha() and w.islower())]
        if falsch:
            raise ValueError(f"Sprachen als zwei Kleinbuchstaben nach ISO 639-1 (de, en, fr), nicht {', '.join(falsch)}")
        return werte


class FaehigkeitsprobeEintrag(BaseModel):
    """Ergebnis der letzten Probe einer Fähigkeit eines Modells (von Hand ausgelöst, PROTOKOLL 4.8)."""

    familie: str
    faehigkeit: Faehigkeit
    belegt: bool                       # die Probe hat die Fähigkeit gezeigt; falsch: abgelehnt oder falsch beantwortet
    zeit_s: float
    meldung: str = ""


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


class Schlafstand(BaseModel):
    """Rechner, die sich schlafen gelegt haben (Kennung, seit wann); übersteht einen Neustart der Leitstelle."""

    seit_s: dict[str, float] = Field(default_factory=dict)


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
