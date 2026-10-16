"""Kanal `/api/kanal` (WebSocket) für die Oberfläche: Umschläge des Protokolls in Echtzeit.

Beim Verbinden kommt sofort das Lagebild, danach jedes Ereignis und höchstens einmal je Sekunde ein
neues Lagebild, wenn sich etwas geändert hat. Anmeldung von Anwendungen über denselben Kanal folgt mit
dem Signalkanal (UMBAU Stufe 3); bis dahin wird Eingehendes gelesen und ignoriert.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..fach.lagebild import lagebild
from ..protokoll.umschlag import umschlag

router = APIRouter()


@router.websocket("/api/kanal")
async def kanal(ws: WebSocket) -> None:
    app = ws.app
    if not app.state.konfig.erlaubt(ws.client.host if ws.client else None):
        await ws.close(code=4403, reason="Nur aus dem Heimnetz oder über VPN")
        return
    await ws.accept()
    betrieb = app.state.betrieb
    q = app.state.bus.abonnieren()
    gesendet = -1

    async def lesen() -> None:
        while True:
            await ws.receive_text()

    leser = asyncio.create_task(lesen())
    try:
        while not leser.done():
            if betrieb.aenderung != gesendet:
                gesendet = betrieb.aenderung
                await ws.send_text(umschlag("leitstelle.lagebild", lagebild(betrieb)).model_dump_json())
            try:
                u = await asyncio.wait_for(q.get(), timeout=1.0)
            except TimeoutError:
                continue
            if u.art != "leitstelle.takt":
                await ws.send_text(u.model_dump_json())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        app.state.bus.abmelden(q)
        leser.cancel()
        with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
            await leser
