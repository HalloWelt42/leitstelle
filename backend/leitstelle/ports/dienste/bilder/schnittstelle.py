"""Schnittstelle der Bildabläufe (PROTOKOLL 6, `POST /v1/images/generations`).

Ein Bildablauf übersetzt einen allgemeinen Bildauftrag (Beschreibung, Größe, Anzahl, Startwert, Schritte) in den Ablauf
genau einer Art von Bilddienst und liefert die fertigen Bilder. Er spricht den Dienst nur über `Senden` an, also über die
Durchleitung des Dienst-Adapters (beim Maschinenraum: über dessen Durchleitung auf dem Rechner). Starten, Speicher,
Rechte und Warteschlange bleiben bei der Leitstelle; der Ablauf kennt nur die Schnittstelle des Dienstes. Sagt der Dienst
selbst, was sein Modell annimmt, liest der Ablauf das als Bild-Steckbrief.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from pydantic import BaseModel, Field

from ....protokoll.steckbrief import Bildsteckbrief
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
    schritte: int | None = Field(default=None, ge=1)    # None: wie der Ablauf oder der Dienst es vorgibt


class Bildergebnis(BaseModel):
    bilder: list[bytes]               # PNG, in der Reihenfolge des Dienstes
    seed: int
    schritte: int | None = None       # wie gerechnet; None: der Dienst hat nach eigener Vorgabe gerechnet


class Bildablauf(Protocol):
    async def erzeugen(self, senden: Senden, auftrag: Bildauftrag) -> Bildergebnis: ...

    async def steckbrief(self, senden: Senden) -> Bildsteckbrief | None:
        """Was das Modell des Dienstes annimmt, wie der Dienst es sagt; None, wenn er nichts sagt."""
        ...
