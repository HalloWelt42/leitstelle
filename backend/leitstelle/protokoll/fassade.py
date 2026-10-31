"""Formen der Fassade, die die Leitstelle selbst festlegt (PROTOKOLL 6): Bilder erzeugen im OpenAI-Format und die
Liste der Dienste. Unbekannte Felder einer Anfrage werden überlesen (PROTOKOLL 1.4). Ob eine Größe, Anzahl oder Zahl der
Schritte zum Bildmodell passt, prüfen die Bildregeln (fach/bildregeln.py) mit dem Steckbrief des Modells; hier steht nur
die Form."""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..kern.werte import Faehigkeit
from ..ports.dienste.bilder import SEED_GRENZE
from .steckbrief import ANZAHL_MAX, Bildsteckbrief

GROESSE = re.compile(r"(\d{1,5})x(\d{1,5})")


def groesse_lesen(groesse: str) -> tuple[int, int]:
    """Breite und Höhe aus "BxH" (die Form ist schon geprüft)."""
    breite, hoehe = groesse.strip().split("x")
    return int(breite), int(hoehe)


class BildAnfrage(BaseModel):
    """`POST /v1/images/generations`: Beschreibung, Größe als "BxH", Anzahl, Startwert, Schritte; Antwort nur als b64_json."""

    model_config = ConfigDict(extra="ignore")

    prompt: str = Field(min_length=1, max_length=20000)
    size: str | None = None                      # None: die Vorgabe des Modells (Steckbrief), sonst 1024x1024
    n: int = Field(default=1, ge=1, le=ANZAHL_MAX)
    seed: int | None = Field(default=None, ge=0, lt=SEED_GRENZE)
    steps: int | None = Field(default=None, ge=1)  # None: die Vorgabe des Modells; Grenzen im Steckbrief (die Bildschmiede rechnet mit ihren)
    model: str | None = None                     # das Bildmodell, die Wahl der Anwendung (Kennung des Dienstes oder Name seines Modells)
    alternativen: list[str] = Field(default_factory=list, max_length=8)   # weitere Bildmodelle der Anwendung, in ihrer Reihenfolge
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
