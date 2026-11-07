"""Formen der Fassade, die die Leitstelle selbst festlegt (PROTOKOLL 6): Bilder erzeugen im OpenAI-Format und die
Liste der Dienste. Unbekannte Felder einer Anfrage werden überlesen (PROTOKOLL 1.4). Ob eine Größe, Anzahl oder Zahl der
Schritte zum Bildmodell passt, prüfen die Bildregeln (fach/bildregeln.py) mit dem Steckbrief des Modells; hier steht nur
die Form."""

from __future__ import annotations

import base64
import binascii
import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..kern.werte import Auftragszustand, Faehigkeit, Prioritaet
from ..ports.dienste.bilder import SEED_GRENZE
from .steckbrief import ANZAHL_MAX, Bildsteckbrief

GROESSE = re.compile(r"(\d{1,5})x(\d{1,5})")
VORLAGE_BYTES_MAX = 20 * 1024 * 1024          # je Bildvorlage


def groesse_lesen(groesse: str) -> tuple[int, int]:
    """Breite und Höhe aus "BxH" (die Form ist schon geprüft)."""
    breite, hoehe = groesse.strip().split("x")
    return int(breite), int(hoehe)


class Modellwahl(BaseModel):
    """Die Wahl der Anwendung in jeder Anfrage: ihr Modell und ihre Ausweichliste, in ihrer Reihenfolge. Die Leitstelle
    wählt nie ein Modell; ohne `model` lehnt sie mit `modell_fehlt` ab, ausgewichen wird nur auf `alternativen`."""

    model_config = ConfigDict(extra="ignore")

    model: str | None = None                     # Kennung des Modells oder Dienstes, ein Alias oder der Name des Modells
    alternativen: list[str] = Field(default_factory=list, max_length=8)   # weitere Modelle der Anwendung, in ihrer Reihenfolge


class BildAnfrage(Modellwahl):
    """`POST /v1/images/generations`: Beschreibung, Größe als "BxH", Anzahl, Startwert, Schritte; Antwort nur als b64_json."""

    prompt: str = Field(min_length=1, max_length=20000)
    size: str | None = None                      # None: die Vorgabe des Modells (Steckbrief), sonst 1024x1024
    n: int = Field(default=1, ge=1, le=ANZAHL_MAX)
    seed: int | None = Field(default=None, ge=0, lt=SEED_GRENZE)
    steps: int | None = Field(default=None, ge=1)  # None: die Vorgabe des Modells; Grenzen im Steckbrief (die Bildschmiede rechnet mit ihren)
    images: list[str] = Field(default_factory=list, max_length=ANZAHL_MAX)  # Bildvorlagen als Base64 (Stil, Bezug); nur Modelle, die bearbeiten
    response_format: str = "b64_json"
    stream: bool = False

    @field_validator("prompt")
    @classmethod
    def _nicht_leer(cls, wert: str) -> str:
        if not wert.strip():
            raise ValueError("Die Beschreibung ist leer.")
        return wert

    @field_validator("size")
    @classmethod
    def _groesse(cls, wert: str | None) -> str | None:
        if wert is None:
            return None
        if not GROESSE.fullmatch(wert.strip()) or 0 in groesse_lesen(wert):
            raise ValueError("Größe als BreitexHöhe in Pixeln, zum Beispiel 1344x768.")
        return wert.strip()

    @field_validator("response_format")
    @classmethod
    def _format(cls, wert: str) -> str:
        if wert != "b64_json":
            raise ValueError("Die Leitstelle liefert Bilder nur als b64_json.")
        return wert

    @field_validator("images")
    @classmethod
    def _vorlagen(cls, werte: list[str]) -> list[str]:
        for i, wert in enumerate(werte, start=1):
            try:
                roh = base64.b64decode(wert, validate=True)
            except (binascii.Error, ValueError):
                raise ValueError(f"Vorlage {i} ist kein Base64.") from None
            if len(roh) > VORLAGE_BYTES_MAX:
                raise ValueError(f"Vorlage {i} ist größer als {VORLAGE_BYTES_MAX // (1024 * 1024)} MB.")
        return werte

    def vorlagen(self) -> list[bytes]:
        """Die Bildvorlagen als Dateiinhalt (die Form ist schon geprüft)."""
        return [base64.b64decode(w) for w in self.images]


class BildDaten(BaseModel):
    b64_json: str
    revised_prompt: str | None = None


class BildZusatz(BaseModel):
    seed: int                         # mit derselben Beschreibung: dasselbe Bild
    modell: str                       # Kennung des Dienstes; als `model` mitgeschickt rechnet derselbe wieder
    groesse: str                      # "BxH", wie gerechnet (ohne `size` die Vorgabe des Modells)
    schritte: int | None              # wie gerechnet (die Bildschmiede: die Schritte ihres Ablaufs); None: nach Vorgabe des Dienstes
    dauer_ms: int                     # Rechenzeit im Dienst, ohne Warten auf Start oder Platz


class BildAntwort(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    created: int
    data: list[BildDaten]
    x_leitstelle: BildZusatz = Field(alias="x-leitstelle")


class Bereitschaft(str, Enum):
    """Zustand eines Dienstes aus Sicht einer Anwendung."""

    BEREIT = "bereit"                 # läuft und nimmt Aufträge an
    STARTET = "startet"               # wird gerade gestartet
    AUS = "aus"                       # läuft nicht; der erste Auftrag startet ihn (Startzeit beachten)
    SCHLAEFT = "schlaeft"             # sein Rechner schläft; Aufträge warten, bis er wach ist
    NICHT_ERREICHBAR = "nicht_erreichbar"   # sein Maschinenraum meldet sich nicht


class DienstSicht(BaseModel):
    """Ein Eintrag von `GET /v1/dienste`: ein Dienst im Maschinenraum, gleich auf wie vielen Rechnern er läuft."""

    kennung: str                      # für `/v1/dienste/<kennung>/...` und als `model`
    name: str                         # der echte Modellname (Whisper Large V3); ohne Modell die Aufgabe
    aufgabe: str = ""                 # wofür er da ist (Spracherkennung), klein hinter dem Namen; leer, wenn der Name es sagt
    zweck: str                        # ein Satz aus dem Steckbrief: wofür er gemacht ist ("" ohne Angabe)
    faehigkeiten: list[Faehigkeit]
    zustand: Bereitschaft
    rechner: list[str]                # Namen der Rechner, auf denen er liegt
    bild: Bildsteckbrief | None = None   # Bilddienste: was ihr Modell annimmt (Größen, Schritte, Anzahl), sobald er einmal lief


class DienstListe(BaseModel):
    object: str = "list"
    data: list[DienstSicht]


# ── Auskunft für Apps (PROTOKOLL 6.5, Arbeitslogik 07.11.2026, LS-18) ────────────────────────────────────────────────
# Was jede App über das Haus lesen darf: Auslastung je App, Modelle je Rechner, geschätzte Dauer, Rangfolge und Priorität.
# Nie Titel, Texte oder Eingaben eines Auftrags.

class AuftragAuskunft(BaseModel):
    """Ein offener Auftrag, ohne Inhalt."""

    kennung: str
    eigener: bool                       # gehört der fragenden App
    faehigkeit: Faehigkeit
    rang: int                           # Rang der Fähigkeit (Regelwerk "Rangfolge"), kleiner kommt zuerst
    prioritaet: Prioritaet              # wie die App sie geschickt hat
    zustand: Auftragszustand
    modell: str | None                  # Familie, sobald zugeteilt oder verlangt
    modell_name: str | None
    rechner: str | None                 # Name des Rechners, auf dem er rechnet
    seit_s: float                       # Sekunden seit Eingang
    rest_s: float | None                # rechnet: geschätzte Restdauer; wartet: voraussichtliche Wartezeit; None: unbekannt


class AppAuskunft(BaseModel):
    name: str
    eigene: bool
    laufend: int
    wartend: int
    auftraege: list[AuftragAuskunft]


class ModellAuskunft(BaseModel):
    familie: str
    name: str
    zustand: str                        # geladen, rechnet, laedt
    auftraege: int                      # laufende und zugeteilte


class RechnerAuskunft(BaseModel):
    name: str
    erreichbar: bool
    schlaeft: bool
    cpu_prozent: float | None
    frei_gb: float
    budget_gb: float
    akku_prozent: int | None
    akku_gesperrt: bool                 # nimmt wegen des Akkus keine neue Arbeit an
    akku_probe: bool = False            # der Ladestand ist ein Probewert einer Abnahme (LS-20)
    vorrang: str | None                 # hat gerade Arbeit mit Vorrang (etwa "Stimme"); Niedrigeres geht anderswohin
    bevorzugt_fuer: list[Faehigkeit]    # Rolle des Rechners
    modelle: list[ModellAuskunft]       # geladen, rechnend oder ladend


class PruefungAuskunft(BaseModel):
    """Offenes Prüffenster einer Abnahme (LS-20): neue Arbeit anderer Apps wartet bis `bis_s`, außer `durchlass`."""

    anwendung: str
    bis_s: float
    durchlass: list[Faehigkeit]


class Lageauskunft(BaseModel):
    """`GET /v1/lage` und je Änderung im Strom `GET /v1/lage/strom`."""

    fassung: str
    zeit_s: float
    hauptregler: str                    # normal, auslaufen, halt
    lage: str                           # ruhig, angespannt, ...
    rangfolge: dict[Faehigkeit, int]
    apps: list[AppAuskunft]
    rechner: list[RechnerAuskunft]
    pruefung: PruefungAuskunft | None = None
