"""Schnittstelle der Dienst-Adapter (ARCHITEKTUR Abschnitt 6, ANBINDUNG Abschnitt 6).

Ein Adapter übersetzt zwischen der Leitstelle und genau einer Art von Dienst. Er meldet Zustand und
Modelle (ohne je etwas zu laden), lädt und entlädt auf Befehl und leitet Anfragen durch. Fehler kommen
als `DienstFehler` mit einem Wort als Grund und dem Wortlaut des Dienstes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from pydantic import BaseModel, Field

from ...kern.werte import Faehigkeit


class ModellBericht(BaseModel):
    schluessel: str                     # Kennung beim Dienst (zum Laden und für Anfragen)
    name: str                           # Anzeigename beim Dienst
    faehigkeiten: set[Faehigkeit]
    gb: float                           # Größe der Gewichte; 0 heißt unbekannt
    parameter_mrd: float | None = None  # None heißt unbekannt; die Leitstelle schützt solche Modelle
    geladen: bool = False
    instanzen: list[str] = Field(default_factory=list)
    plaetze: int | None = None          # gleichzeitige Anfragen je Instanz, wenn der Dienst es meldet
    kontext: int | None = None
    einbettung: bool = False
    gb_jetzt: float | None = None       # tatsächlich belegt, wenn der Dienst es misst (sonst gilt gb)
    schutz: bool | None = None          # vom Dienst vorgegeben; None: Regel nach Parameterzahl
    aktiv: bool = False                 # arbeitet gerade, auch ohne Auftrag über die Leitstelle


class Dienstbericht(BaseModel):
    erreichbar: bool
    steuerbar: bool = False             # kann laden und entladen und meldet echten Ladezustand
    modelle: list[ModellBericht] = Field(default_factory=list)
    meldung: str = ""


class Durchleitung(BaseModel):
    """Eine Anfrage, die unverändert an einen Dienst geht (Fassade `/v1/dienste/<name>/<pfad>`)."""

    methode: str
    pfad: str                           # ohne führenden Schrägstrich, relativ zum Dienst
    abfrage: str = ""                   # Teil nach dem Fragezeichen
    kopf: dict[str, str] = Field(default_factory=dict)
    inhalt: bytes = b""


class DienstFehler(Exception):
    """Der Dienst hat abgelehnt oder ist gestört. `grund` ist ein Wort aus PROTOKOLL.md Abschnitt 7."""

    def __init__(self, grund: str, meldung: str, wiederholbar: bool = False) -> None:
        super().__init__(meldung)
        self.grund = grund
        self.meldung = meldung
        self.wiederholbar = wiederholbar


class Strom(Protocol):
    """Antwort eines Dienstes, die durchgeleitet wird. Arbeit hat keine Lese-Zeitgrenze."""

    status: int
    kopf: dict[str, str]

    def zeilen(self) -> AsyncIterator[bytes]: ...
    def stuecke(self) -> AsyncIterator[bytes]: ...
    async def lesen(self) -> bytes: ...
    async def schliessen(self) -> None: ...


class DienstAdapter(Protocol):
    async def zustand(self) -> Dienstbericht: ...
    async def laden(self, schluessel: str) -> str: ...
    async def entladen(self, instanz: str) -> None: ...
    async def anfrage(self, pfad: str, koerper: dict[str, Any]) -> Strom: ...
    async def durchleiten(self, schluessel: str, d: Durchleitung) -> Strom: ...
    async def schliessen(self) -> None: ...
