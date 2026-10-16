"""Startet eine ASGI-Anwendung auf einem freien Port im laufenden Ereignisschleifen-Kontext der Tests.

Echte Verbindungen statt In-Prozess-Transport: nur so sind Ströme, Abbrüche und gleichzeitige
Anfragen so wie im Betrieb.
"""

from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager

import uvicorn


@asynccontextmanager
async def laufend(app):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="on"))
    aufgabe = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        await asyncio.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await aufgabe
        sock.close()
