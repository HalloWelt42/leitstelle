"""Nutzlasten der Knoten-Agenten (PROTOKOLL.md Abschnitt 4.2).

Der Agent ist ein eigenes Paket ohne Abhängigkeit zum Kern; er führt dieselben Modelle in
`agent/leitstelle_agent/protokoll.py`. Ein Test hält beide Seiten deckungsgleich.
Fehlende Messwerte bleiben None (weggelassen, nicht genullt).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ..kern.werte import Faehigkeit


class KnotenAnmeldung(BaseModel):
    """`knoten.anmelden`: wer der Agent ist und was er messen kann."""

    name: str
    betriebssystem: str
    architektur: str
    speicher_gb: float
    agent_version: str
    messwege: list[str] = Field(default_factory=list)
    durchleitung_port: int | None = None    # Port, über den die Leitstelle Anfragen an die Dienste durchreicht


class Messwerte(BaseModel):
    """`knoten.messwerte`: im Takt des Agenten."""

    speicher_gesamt_gb: float
    speicher_belegt_gb: float
    swap_belegt_gb: float | None = None
    swap_gesamt_gb: float | None = None
    cpu_prozent: float | None = None
    last_1m: float | None = None
    platte_frei_gb: float | None = None
    grafik_prozent: float | None = None
    temperatur_c: float | None = None
    leistung_w: float | None = None


class Prozesszustand(str, Enum):
    AUS = "aus"
    STARTET = "startet"
    LAEUFT = "laeuft"
    STOPPT = "stoppt"
    GESTOERT = "gestoert"


class ProzessBericht(BaseModel):
    """Ein Dienst, den der Agent verwaltet (eine Datei in seinem Ordner `dienste/`)."""

    kennung: str
    name: str
    faehigkeiten: set[Faehigkeit]
    port: int | None = None
    zustand: Prozesszustand
    fremd: bool = False                 # läuft, aber nicht vom Agenten gestartet
    gb_jetzt: float | None = None       # gemessen, solange er läuft; sonst None
    bedarf_gb: float                    # was er bei der Arbeit braucht (80-%-Wert seiner Arbeitsspitzen, mindestens die Schätzung)
    aktiv: bool = False                 # arbeitet gerade (Prozessorlast über der Schwelle des Dienstes)
    anhalten_erlaubt: bool = True       # darf die Leitstelle ihn anhalten, um Speicher freizumachen
    plaetze: int = 1                    # so viele Anfragen nimmt er gleichzeitig an
    meldung: str = ""


class Dienstliste(BaseModel):
    """`knoten.dienste`: vollständiger Stand aller verwalteten Dienste, bei jeder Änderung."""

    dienste: list[ProzessBericht] = Field(default_factory=list)


class Befehlsart(str, Enum):
    DIENST_STARTEN = "dienst_starten"
    DIENST_ANHALTEN = "dienst_anhalten"


class Befehl(BaseModel):
    """`knoten.befehl`: begrenzt auf die Dienstverwaltung."""

    befehl: Befehlsart
    ziel: str


class BefehlErgebnis(BaseModel):
    """`knoten.befehl_ergebnis`, mit `bezug` auf den Befehl."""

    befehl: Befehlsart
    ziel: str
    erfolg: bool
    meldung: str = ""
