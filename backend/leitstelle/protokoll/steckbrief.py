"""Steckbrief je Modell (PROTOKOLL.md Abschnitt 4.8): wofür ein Modell gemacht ist, was es kann und wie es sich im
Betrieb verhält. Eine App fragt danach, statt Modellnamen zu kennen.

Die Leitstelle setzt ihn aus drei Quellen zusammen und nennt je Angabe die Herkunft: was der Dienst selbst sagt
(`Selbstauskunft`), was von Hand eingetragen ist (geht vor), was sie misst. Abgeleitet heißt: aus anderen Angaben
geschlossen (etwa "lange Texte" aus einem großen Kontext).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ..kern.werte import Eignung, Faehigkeit, Zone


class Quelle(str, Enum):
    DIENST = "dienst"                 # der Dienst sagt es selbst (Modell-Läufer, Dienstdatei des Maschinenraums, Anbieter)
    HAND = "hand"                     # in der Leitstelle eingetragen
    GEMESSEN = "gemessen"             # aus dem Verlauf der Leitstelle
    ABGELEITET = "abgeleitet"         # aus anderen Angaben geschlossen


class Messwerte(BaseModel):
    """Aus den jüngsten fertigen Aufträgen des Modells (Mittelwerte als Median, Ladezeit als gleitender Mittelwert)."""

    auftraege: int = 0                # Grundlage
    rechenzeit_s: float | None = None
    erstes_stueck_s: float | None = None
    token_je_s: float | None = None   # erzeugte Token je Sekunde nach dem ersten Stück
    ladezeit_s: float | None = None


class Steckbrief(BaseModel):
    zweck: str = ""                                          # ein Satz: wofür gemacht oder optimiert
    eignung: list[Eignung] = Field(default_factory=list)
    sprachen: list[str] = Field(default_factory=list)        # ISO 639-1; leer: nicht angegeben
    faehigkeiten: list[Faehigkeit] = Field(default_factory=list)
    kontext: int | None = None                               # Token
    parameter_mrd: float | None = None
    quantisierung: str | None = None
    zone: Zone = Zone.HEIM                                   # wo gerechnet wird; extern heißt: Daten verlassen das Heimnetz
    anfragen_je_minute: int | None = None                    # Grenze des Anbieters
    gemessen: Messwerte = Field(default_factory=Messwerte)
    herkunft: dict[str, Quelle] = Field(default_factory=dict)   # je Angabe, woher sie stammt
