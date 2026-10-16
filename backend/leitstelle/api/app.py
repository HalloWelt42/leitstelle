"""Zusammenbau des Kern-Dienstes: Ablage öffnen (Migrationen), Betrieb starten, Router und Oberfläche."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from .. import version
from ..fach.betrieb import Betrieb
from ..fach.ereignisse import Ereignisbus
from ..fach.verzeichnis import Verzeichnis
from ..fach.vermittlung import Vermittlung
from ..konfig import Konfig
from ..ports.ablage.datenbank import Datenbank
from ..ports.ablage.repositorien import Ablage
from ..ports.dienste import adapter_fabrik
from ..ports.tresor import Tresor
from ..ports.uhr import Systemuhr, Uhr
from . import fassade, kanal, verwaltung


def erstellen(konfig: Konfig | None = None, uhr: Uhr | None = None, transport: httpx.AsyncBaseTransport | None = None, mit_takt: bool = True) -> FastAPI:
    konfig = konfig or Konfig()

    @asynccontextmanager
    async def lebenslauf(app: FastAPI):
        konfig.daten.mkdir(parents=True, exist_ok=True)
        db = Datenbank(konfig.datenbank)
        await db.oeffnen()
        bus = Ereignisbus()
        betrieb = Betrieb(Ablage(db), Tresor(konfig.tresor_schluessel), uhr or Systemuhr(), adapter_fabrik(konfig.verbindung_s, transport), bus, konfig)
        app.state.konfig, app.state.bus, app.state.betrieb = konfig, bus, betrieb
        app.state.vermittlung = Vermittlung(betrieb, konfig)
        app.state.verzeichnis = Verzeichnis(betrieb)
        await betrieb.starten(mit_schleife=mit_takt)
        logging.getLogger("leitstelle").info("Leitstelle %s bereit auf Port %s, Daten in %s", version(), konfig.port, konfig.daten)
        try:
            yield
        finally:
            await betrieb.beenden()
            await db.schliessen()

    app = FastAPI(title="Leitstelle", version=version(), lifespan=lebenslauf)

    @app.exception_handler(HTTPException)
    async def http_fehler(_request: Request, fehler: HTTPException):
        if isinstance(fehler.detail, dict):
            return JSONResponse(fehler.detail, status_code=fehler.status_code)
        return JSONResponse({"grund": "fehler", "begruendung": str(fehler.detail)}, status_code=fehler.status_code)

    @app.get("/gesundheit", include_in_schema=False)
    async def gesundheit():
        return {"zustand": "ok", "version": version()}

    app.include_router(fassade.router)
    app.include_router(verwaltung.router)
    app.include_router(kanal.router)
    _oberflaeche(app, konfig)
    return app


def _oberflaeche(app: FastAPI, konfig: Konfig) -> None:
    """Liefert die gebaute Oberfläche aus; unbekannte Pfade bekommen index.html (Router im Browser)."""
    wurzel = konfig.oberflaeche
    if wurzel is None or not (wurzel / "index.html").exists():
        return
    wurzel = wurzel.resolve()

    @app.get("/{pfad:path}", include_in_schema=False)
    async def seite(pfad: str, request: Request):
        if not konfig.erlaubt(request.client.host if request.client else None):
            return JSONResponse({"grund": "herkunft_nicht_erlaubt", "begruendung": "Nur aus dem Heimnetz oder über VPN erreichbar."}, status_code=403)
        datei = (wurzel / pfad).resolve()
        if pfad and datei.is_file() and Path(datei).is_relative_to(wurzel):
            kopf = {"Cache-Control": "public, max-age=604800, immutable"} if "/assets/" in f"/{pfad}" else {"Cache-Control": "no-cache"}
            return FileResponse(datei, headers=kopf)
        return FileResponse(wurzel / "index.html", headers={"Cache-Control": "no-cache"})
