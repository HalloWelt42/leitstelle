"""Der Agentenordner: ein Ort je Rechner für alles, was der Agent verwaltet.

    <ordner>/agent.toml          Adresse der Leitstelle, Takt, Neustartregeln
    <ordner>/schluessel          Schlüssel des Agenten (nur für den Benutzer lesbar)
    <ordner>/dienste/<name>.toml je Dienst eine Datei; der Dateiname ist die Kennung
    <ordner>/protokolle/         Ausgabe des Agenten und je Dienst eine Datei
    <ordner>/zustand.json        Sollzustand je Dienst (übersteht Neustarts) und gemessene Höchstwerte
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from .protokoll import Faehigkeit

KENNUNG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
STANDARD_PFAD = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def _pfad(wert: str) -> Path:
    return Path(os.path.expandvars(wert)).expanduser()


class AgentKonfig(BaseModel):
    leitstelle: str = Field(description="Basisadresse der Leitstelle, zum Beispiel http://leitstelle:8530")
    name: str | None = Field(default=None, description="Anzeigename des Rechners; sonst der Rechnername")
    takt_s: float = Field(default=5.0, ge=1, le=300, description="Abstand der Messungen und der Dienstprüfung")
    neustart_pausen_s: list[float] = Field(default=[5, 30, 120], min_length=1, description="Pausen vor dem 1., 2., 3. Neustart nach einem Absturz")
    neustart_fenster_s: float = Field(default=600, gt=0, description="Zeitraum, in dem Abstürze gezählt werden")
    neustarts_im_fenster: int = Field(default=3, ge=0, description="mehr Abstürze im Zeitraum: der Dienst bleibt aus")
    wiederverbindung_max_s: float = Field(default=30, ge=1, description="längste Pause zwischen Verbindungsversuchen")
    macmon: bool = Field(default=True, description="Zusatzmessungen (Grafik, Temperatur, Leistung) über macmon, wenn vorhanden")

    @property
    def kanal(self) -> str:
        basis = self.leitstelle.rstrip("/")
        return "ws" + basis[4:] + "/agent/kanal" if basis.startswith("http") else basis + "/agent/kanal"


class DienstVorlage(BaseModel):
    """Eine Datei unter dienste/. Der Dienst läuft in eigener Sitzung (Prozessgruppe), eigenem Arbeitsordner, mit
    eigener Umgebung (nur Pfad, Heimordner, Sprache und was hier steht) und eigener Protokolldatei."""

    kennung: str
    name: str
    ordner: Path
    befehl: list[str] = Field(min_length=1)
    vorher: list[str] = Field(default_factory=list, description="Befehl, der vor jedem Start einmal läuft (zum Beispiel Härtung)")
    port: int | None = Field(default=None, ge=1, le=65535)
    pruefadresse: str | None = Field(default=None, description="erreichbar heißt: Antwort unter 500; sonst reicht der offene Port")
    faehigkeiten: set[Faehigkeit] = Field(default_factory=set)
    speicher_gb: float = Field(default=1.0, ge=0, description="Schätzung bis zur ersten Messung")
    startzeit_s: float = Field(default=120, gt=0, description="so lange darf der Start bis zur Erreichbarkeit dauern")
    anhaltezeit_s: float = Field(default=20, gt=0, description="so lange darf das Beenden dauern, danach hart")
    umgebung: dict[str, str] = Field(default_factory=dict)
    umgebung_datei: Path | None = Field(default=None, description="Datei mit Zeilen NAME=WERT, zum Beispiel die .env des Projekts")
    pfad: str = STANDARD_PFAD
    neustart: bool = Field(default=True, description="nach einem Absturz neu starten, solange er laufen soll")

    @field_validator("ordner", "umgebung_datei", mode="before")
    @classmethod
    def _aufloesen(cls, wert: object) -> object:
        return _pfad(wert) if isinstance(wert, str) else wert

    @field_validator("kennung")
    @classmethod
    def _kennung(cls, wert: str) -> str:
        if not KENNUNG.match(wert):
            raise ValueError("Dateiname nur aus Kleinbuchstaben, Ziffern, - und _")
        return wert

    def programm(self, umgebung: dict[str, str]) -> list[str]:
        """Befehl mit aufgelösten Variablen aus der Umgebung des Dienstes; ein relatives Programm gilt ab `ordner`."""
        teile = [erweitern(t, umgebung) for t in self.befehl]
        if "/" in teile[0] and not os.path.isabs(teile[0]):
            teile[0] = str(self.ordner / teile[0])
        return teile


class Ladefehler(BaseModel):
    datei: str
    meldung: str


class Agentenordner:
    def __init__(self, wurzel: Path) -> None:
        self.wurzel = wurzel.expanduser().resolve()

    @property
    def dienste_ordner(self) -> Path:
        return self.wurzel / "dienste"

    @property
    def protokolle(self) -> Path:
        return self.wurzel / "protokolle"

    @property
    def zustand_datei(self) -> Path:
        return self.wurzel / "zustand.json"

    def konfig(self) -> AgentKonfig:
        with open(self.wurzel / "agent.toml", "rb") as f:
            return AgentKonfig.model_validate(tomllib.load(f))

    def schluessel(self) -> str:
        return (self.wurzel / "schluessel").read_text(encoding="utf-8").strip()

    def dienste(self) -> tuple[list[DienstVorlage], list[Ladefehler]]:
        """Alle Dienstdateien; fehlerhafte werden gemeldet und ausgelassen, nie geraten."""
        vorlagen, fehler = [], []
        for datei in sorted(self.dienste_ordner.glob("*.toml")):
            try:
                with open(datei, "rb") as f:
                    vorlagen.append(DienstVorlage.model_validate({**tomllib.load(f), "kennung": datei.stem}))
            except (OSError, tomllib.TOMLDecodeError, ValidationError) as e:
                fehler.append(Ladefehler(datei=datei.name, meldung=str(e).splitlines()[0][:200]))
        return vorlagen, fehler


def erweitern(text: str, umgebung: dict[str, str]) -> str:
    """~ am Anfang und $NAME oder ${NAME} aus der gegebenen Umgebung (nicht der des Agenten); Unbekanntes bleibt stehen."""
    text = re.sub(r"\$(?:\{(\w+)\}|(\w+))", lambda m: umgebung.get(m.group(1) or m.group(2), m.group(0)), text)
    return str(Path(text).expanduser()) if text.startswith("~") else text


def umgebung_lesen(datei: Path) -> dict[str, str]:
    """Zeilen NAME=WERT, Kommentare mit #, Werte ohne umschließende Anführungszeichen."""
    werte: dict[str, str] = {}
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        name, _, wert = zeile.partition("=")
        name = name.removeprefix("export ").strip()
        wert = wert.strip()
        if len(wert) >= 2 and wert[0] == wert[-1] and wert[0] in "\"'":
            wert = wert[1:-1]
        werte[name] = wert
    return werte
