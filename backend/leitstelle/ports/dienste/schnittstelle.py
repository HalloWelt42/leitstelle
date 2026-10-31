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
from ...protokoll.knoten import Selbstauskunft


class ModellBericht(BaseModel):
    schluessel: str                     # Kennung beim Dienst (zum Laden und für Anfragen)
    name: str                           # Anzeigename beim Dienst (bei Maschinenraum-Diensten der Modellname)
    aufgabe: str = ""                   # wofür er da ist, wie der Dienst es nennt (Spracherkennung); leer: sagt nichts
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
    selbstauskunft: Selbstauskunft = Field(default_factory=Selbstauskunft)   # was der Dienst über das Modell sagt
    familie: str | None = None          # weitere Instanz: Familie der Grundinstanz (sonst gilt der Schlüssel)
    instanzen_hoechstens: int = 1       # so viele Instanzen darf die Leitstelle starten
    sperre: str | None = None           # vom Dienst gesperrt (Speicherabbruch im Maschinenraum): der Grund; nicht nutzbar, bis ein Mensch sie dort aufhebt


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


class Verbrauch(BaseModel):
    """Token einer Antwort, wie der Dienst sie nennt (`usage`); None: nicht genannt."""

    token_ein: int | None = None
    token_aus: int | None = None


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
    verbrauch: Verbrauch | None         # Token der Antwort, sobald der Dienst sie genannt hat (sonst None)

    def zeilen(self) -> AsyncIterator[bytes]: ...
    def stuecke(self) -> AsyncIterator[bytes]: ...
    async def lesen(self) -> bytes: ...
    async def schliessen(self) -> None: ...


class DienstAdapter(Protocol):
    meldet_sich_selbst: bool            # True: Zustand kommt vom Dienst (Knoten-Agent), sonst fragt die Leitstelle nach
    ueberlast_status: frozenset[int]    # Antwortcodes, mit denen der Dienst vorübergehende Überlast meldet (kein Fehlschlag)
    async def zustand(self) -> Dienstbericht: ...
    async def laden(self, schluessel: str) -> str: ...
    async def instanz_laden(self, schluessel: str, stufe: int) -> str: ...   # weitere Instanz; liefert ihre Kennung beim Dienst
    async def entladen(self, instanz: str) -> None: ...
    async def anfrage(self, pfad: str, koerper: dict[str, Any]) -> Strom: ...
    async def durchleiten(self, schluessel: str, d: Durchleitung) -> Strom: ...
    async def schliessen(self) -> None: ...
