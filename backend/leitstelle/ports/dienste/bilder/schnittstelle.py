"""Schnittstelle der Bildabläufe (PROTOKOLL 6, `POST /v1/images/generations`).

Ein Bildablauf übersetzt einen allgemeinen Bildauftrag (Beschreibung, Größe, Anzahl, Startwert) in den Ablauf genau
einer Art von Bilddienst und liefert die fertigen Bilder. Er spricht den Dienst nur über `Senden` an, also über die
Durchleitung des Dienst-Adapters (beim Maschinenraum: über dessen Durchleitung auf dem Rechner). Starten, Speicher,
Rechte und Warteschlange bleiben bei der Leitstelle; der Ablauf kennt nur die Schnittstelle des Dienstes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from pydantic import BaseModel, Field

from ..schnittstelle import Durchleitung, Strom

# Größter Startwert: in JSON als ganze Zahl verlustfrei auch für Leser, die Zahlen als Gleitkomma lesen
SEED_GRENZE = 2**53

Senden = Callable[[Durchleitung], Awaitable[Strom]]


class Bildauftrag(BaseModel):
    """Was erzeugt werden soll; der Startwert steht fest (gleicher Startwert und gleiche Beschreibung: gleiches Bild)."""

    beschreibung: str
    breite: int
    hoehe: int
    anzahl: int = Field(ge=1, le=4)
    seed: int = Field(ge=0, lt=SEED_GRENZE)


class Bildergebnis(BaseModel):
    bilder: list[bytes]               # PNG, in der Reihenfolge des Dienstes
    seed: int


class Bildablauf(Protocol):
    async def erzeugen(self, senden: Senden, auftrag: Bildauftrag) -> Bildergebnis: ...
