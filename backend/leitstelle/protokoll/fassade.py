"""Formen der Fassade, die die Leitstelle selbst festlegt (PROTOKOLL 6): Bilder erzeugen im OpenAI-Format und die
Liste der Dienste. Unbekannte Felder einer Anfrage werden überlesen (PROTOKOLL 1.4)."""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..kern.werte import Faehigkeit
from ..ports.dienste.bilder import SEED_GRENZE

GROESSE = re.compile(r"(\d{2,4})x(\d{2,4})")
KANTE_MIN, KANTE_MAX, KANTE_RASTER = 256, 2048, 16


class BildAnfrage(BaseModel):
    """`POST /v1/images/generations`: Beschreibung, Größe als "BxH", Anzahl, Startwert; Antwort nur als b64_json."""

    model_config = ConfigDict(extra="ignore")

    prompt: str = Field(min_length=1, max_length=8000)
    size: str = "1024x1024"
    n: int = Field(default=1, ge=1, le=4)
    seed: int | None = Field(default=None, ge=0, lt=SEED_GRENZE)
    model: str | None = None
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
    def _groesse(cls, wert: str) -> str:
        t = GROESSE.fullmatch(wert.strip())
        if not t or not all(KANTE_MIN <= int(k) <= KANTE_MAX and int(k) % KANTE_RASTER == 0 for k in t.groups()):
            raise ValueError(f"Größe als BreitexHöhe, je {KANTE_MIN} bis {KANTE_MAX} und durch {KANTE_RASTER} teilbar, zum Beispiel 1344x768.")
        return wert.strip()

    @field_validator("response_format")
    @classmethod
    def _format(cls, wert: str) -> str:
        if wert != "b64_json":
            raise ValueError("Die Leitstelle liefert Bilder nur als b64_json.")
        return wert

    @property
    def breite(self) -> int:
        return int(self.size.split("x")[0])

    @property
    def hoehe(self) -> int:
        return int(self.size.split("x")[1])


class BildDaten(BaseModel):
    b64_json: str
    revised_prompt: str | None = None


class BildZusatz(BaseModel):
    seed: int                         # mit derselben Beschreibung: dasselbe Bild
    modell: str                       # Kennung des Dienstes; als `model` mitgeschickt rechnet derselbe wieder
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
    name: str
    faehigkeiten: list[Faehigkeit]
    zustand: Bereitschaft
    rechner: list[str]                # Namen der Rechner, auf denen er liegt


class DienstListe(BaseModel):
    object: str = "list"
    data: list[DienstSicht]
