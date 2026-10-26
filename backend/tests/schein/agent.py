"""Schein-Agent: ein Maschinenraum zum Anfassen für die Tests der Leitstelle (Protokoll PROTOKOLL.md Abschnitt 4.2).

Meldet sich mit seinem Schlüssel an, meldet Messwerte und eine feste Dienstliste, legt sich schlafen wie der echte vor
dem Einschlafen (`knoten.schlaeft`, wartet höchstens 3 s auf `knoten.schlaf_vermerkt`, schließt mit dem Grund
`schlaeft`) und wacht wieder auf (neue Anmeldung). `trennen` reißt die Verbindung ohne Abmeldung ab, wie ein Rechner,
der unangekündigt verschwindet. `fremde_melden` schickt, was seine Beobachtung am Leitstand vorbei sähe. Befehle lehnt er
ab; er startet nichts.
"""

from __future__ import annotations

import asyncio
import contextlib

import websockets
from pydantic import BaseModel

from leitstelle.kern.werte import Faehigkeit
from leitstelle.protokoll.knoten import (Befehl, BefehlErgebnis, Dienstliste, Fremdzugriffe, KnotenAnmeldung, KnotenSchlaeft, Messwerte,
                                         ProzessBericht, Prozesszustand, Schlafgrund)
from leitstelle.protokoll.umschlag import Umschlag

VERMERK_S = 3.0


def probe() -> ProzessBericht:
    """Ein Prozessdienst wie im Maschinenraum: Stimme, aus, braucht wenig."""
    return ProzessBericht(kennung="probe", name="Probe", faehigkeiten={Faehigkeit.STIMME}, zustand=Prozesszustand.AUS, bedarf_gb=0.5)


class ScheinAgent:
    def __init__(self, url: str, schluessel: str, dienste: list[ProzessBericht] | None = None) -> None:
        self.kanal = url.replace("http", "ws", 1) + "/agent/kanal"
        self.schluessel = schluessel
        self.dienste = Dienstliste(dienste=dienste if dienste is not None else [probe()])
        self._ws = None
        self._empfang: asyncio.Task | None = None
        self._angemeldet = asyncio.Event()
        self._offen: dict[str, asyncio.Future[None]] = {}

    async def _senden(self, art: str, nutzlast: BaseModel) -> str:
        u = Umschlag(art=art, von="schein-agent", an="leitstelle", nutzlast=nutzlast.model_dump(mode="json"))
        await self._ws.send(u.model_dump_json())
        return u.id

    async def verbinden(self) -> None:
        self._angemeldet.clear()
        self._ws = await websockets.connect(self.kanal, additional_headers={"Authorization": f"Bearer {self.schluessel}"})
        await self._senden("knoten.anmelden", KnotenAnmeldung(name="Mac Studio", betriebssystem="macOS 15.6", architektur="arm64",
                                                              speicher_gb=64.0, agent_version="schein", messwege=["speicher"]))
        self._empfang = asyncio.create_task(self._empfangen())
        await asyncio.wait_for(self._angemeldet.wait(), 10)
        await self._senden("knoten.messwerte", Messwerte(speicher_gesamt_gb=64.0, speicher_belegt_gb=20.0))
        await self._senden("knoten.dienste", self.dienste)

    async def fremde_melden(self, fremde: Fremdzugriffe) -> None:
        """`knoten.fremde`, wie der Maschinenraum es im Takt der Messung schickt."""
        await self._senden("knoten.fremde", fremde)

    async def wecken(self) -> None:
        """Aufgewacht: wie der Maschinenraum meldet er sich neu an."""
        await self.verbinden()

    async def schlafen(self, grund: Schlafgrund = Schlafgrund.LEERLAUF) -> bool:
        """True, wenn die Leitstelle den Schlaf vermerkt hat; geschlossen wird in jedem Fall."""
        zukunft: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        kennung = await self._senden("knoten.schlaeft", KnotenSchlaeft(grund=grund))
        self._offen[kennung] = zukunft
        try:
            await asyncio.wait_for(zukunft, VERMERK_S)
            vermerkt = True
        except TimeoutError:
            vermerkt = False
        finally:
            self._offen.pop(kennung, None)
        await self._ws.close(1000, "schlaeft")
        await self._ende()
        return vermerkt

    async def trennen(self) -> None:
        """Ohne Abmeldung weg (Stromausfall, Netz weg, Schlaf ohne Meldung)."""
        self._ws.transport.abort()
        await self._ende()

    async def beenden(self) -> None:
        if self._ws is not None:
            with contextlib.suppress(websockets.exceptions.WebSocketException, OSError):
                await self._ws.close()
            await self._ende()

    async def _ende(self) -> None:
        if self._empfang is not None:
            self._empfang.cancel()
            await asyncio.gather(self._empfang, return_exceptions=True)
        self._ws = self._empfang = None

    async def _empfangen(self) -> None:
        with contextlib.suppress(websockets.exceptions.ConnectionClosed):
            async for text in self._ws:
                u = Umschlag.model_validate_json(text)
                if u.art == "knoten.angemeldet":
                    self._angemeldet.set()
                elif u.art == "knoten.schlaf_vermerkt" and (z := self._offen.get(u.bezug or "")) is not None and not z.done():
                    z.set_result(None)
                elif u.art == "knoten.befehl":
                    b = Befehl.model_validate(u.nutzlast)
                    e = BefehlErgebnis(befehl=b.befehl, ziel=b.ziel, erfolg=False, meldung="der Schein-Agent startet nichts")
                    await self._ws.send(Umschlag(art="knoten.befehl_ergebnis", von="schein-agent", an="leitstelle", bezug=u.id,
                                                 nutzlast=e.model_dump(mode="json")).model_dump_json())
