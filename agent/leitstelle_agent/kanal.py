"""Verbindung zur Leitstelle: ausgehend, mit Schlüssel, mit wachsender Pause bei Abbruch.

Nach dem Verbinden: `knoten.anmelden`, dann Messwerte im Takt, die Dienstliste bei jeder Änderung (und
spätestens alle zehn Takte) und Antworten auf Befehle. Ohne Verbindung arbeitet die Dienstverwaltung
unverändert weiter.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import platform
import socket
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import websockets
from pydantic import BaseModel, Field, ValidationError

from . import __version__
from .konfig import AgentKonfig, Agentenordner
from .messen import Messer
from .protokoll import Befehl, KnotenAnmeldung
from .prozesse import Verwalter

log = logging.getLogger("leitstelle_agent")
PROTOKOLL = "leitstelle/1"
DIENSTLISTE_SPAETESTENS = 10                     # Takte


class Umschlag(BaseModel):
    protokoll: str = PROTOKOLL
    art: str
    id: str = Field(default_factory=lambda: uuid4().hex)
    zeit: str = Field(default_factory=lambda: datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"))
    von: str = "agent"
    an: str = "leitstelle"
    bezug: str | None = None
    nutzlast: dict[str, Any] = Field(default_factory=dict)


def _umschlag(art: str, nutzlast: BaseModel, bezug: str | None = None) -> str:
    return Umschlag(art=art, nutzlast=nutzlast.model_dump(mode="json"), bezug=bezug).model_dump_json()


class Kanal:
    def __init__(self, ordner: Agentenordner, konfig: AgentKonfig, verwalter: Verwalter, messer: Messer) -> None:
        self.ordner, self.konfig, self.verwalter, self.messer = ordner, konfig, verwalter, messer

    def anmeldung(self) -> KnotenAnmeldung:
        gesamt = self.messer.messen().speicher_gesamt_gb
        system = f"{platform.system()} {platform.mac_ver()[0] or platform.release()}"
        return KnotenAnmeldung(name=self.konfig.name or socket.gethostname().removesuffix(".local"), betriebssystem=system,
                               architektur=platform.machine(), speicher_gb=gesamt, agent_version=__version__, messwege=self.messer.messwege())

    async def schleife(self) -> None:
        pause = 1.0
        while True:
            try:
                await self._verbunden()
                pause = 1.0
            except websockets.exceptions.InvalidStatus as f:
                log.error("Leitstelle lehnt die Verbindung ab (%s); Schlüssel prüfen", f.response.status_code)
                pause = self.konfig.wiederverbindung_max_s
            except websockets.exceptions.ConnectionClosed as f:
                grund = f.rcvd.reason if f.rcvd else ""
                log.warning("Verbindung zur Leitstelle beendet%s", f": {grund}" if grund else "")
                if grund in ("unbekannter_schluessel", "schluessel_erneuert"):
                    pause = self.konfig.wiederverbindung_max_s
            except (OSError, asyncio.TimeoutError) as f:
                log.warning("Leitstelle nicht erreichbar: %s", f)
            await asyncio.sleep(pause)
            pause = min(pause * 2, self.konfig.wiederverbindung_max_s)

    async def _verbunden(self) -> None:
        kopf = {"Authorization": f"Bearer {self.ordner.schluessel()}"}
        async with websockets.connect(self.konfig.kanal, additional_headers=kopf, open_timeout=10, ping_interval=20) as ws:
            await ws.send(_umschlag("knoten.anmelden", await asyncio.to_thread(self.anmeldung)))
            log.info("Mit der Leitstelle verbunden: %s", self.konfig.leitstelle)
            sperre = asyncio.Lock()

            async def senden(text: str) -> None:
                async with sperre:
                    await ws.send(text)

            empfang = asyncio.create_task(self._empfangen(ws, senden))
            try:
                await self._senden_im_takt(senden, empfang)
            finally:
                empfang.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await empfang
            empfang.result()                                 # Verbindungsfehler des Empfangs weiterreichen

    async def _senden_im_takt(self, senden, empfang: asyncio.Task) -> None:
        takt = 0
        await senden(_umschlag("knoten.dienste", self.verwalter.liste()))
        while not empfang.done():
            await senden(_umschlag("knoten.messwerte", await asyncio.to_thread(self.messer.messen)))
            takt += 1
            if takt % DIENSTLISTE_SPAETESTENS == 0:
                await senden(_umschlag("knoten.dienste", self.verwalter.liste()))
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._aenderung_abwarten(empfang), timeout=self.konfig.takt_s)
                await senden(_umschlag("knoten.dienste", self.verwalter.liste()))
                await asyncio.sleep(0.2)                     # mehrere Änderungen kurz hintereinander zusammenfassen

    async def _aenderung_abwarten(self, empfang: asyncio.Task) -> None:
        warten = asyncio.create_task(self.verwalter.aenderung.wait())
        try:
            await asyncio.wait({warten, empfang}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            warten.cancel()
        self.verwalter.aenderung.clear()
        if empfang.done():
            raise asyncio.TimeoutError

    async def _empfangen(self, ws, senden) -> None:
        aufgaben: set[asyncio.Task] = set()
        async for text in ws:
            try:
                u = Umschlag.model_validate_json(text)
            except ValidationError:
                log.warning("Unlesbare Nachricht der Leitstelle")
                continue
            if u.art == "knoten.befehl":
                t = asyncio.create_task(self._befehl(u, senden))
                aufgaben.add(t)
                t.add_done_callback(aufgaben.discard)
            elif u.art == "knoten.angemeldet":
                log.info("Angemeldet als %s", u.nutzlast.get("name"))

    async def _befehl(self, u: Umschlag, senden) -> None:
        try:
            b = Befehl.model_validate(u.nutzlast)
        except ValidationError as f:
            log.warning("Ungültiger Befehl: %s", f.errors()[:1])
            return
        ergebnis = await self.verwalter.befehl(b)
        with contextlib.suppress(websockets.exceptions.ConnectionClosed):
            await senden(_umschlag("knoten.befehl_ergebnis", ergebnis, bezug=u.id))
