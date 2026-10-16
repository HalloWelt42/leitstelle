"""Knoten-Agenten: Kanal `/agent/kanal` (WebSocket) und Auslieferung von Installationsskript und Paket.

Der Agent verbindet sich von sich aus (ausgehend) mit seinem Schlüssel als Bearer. Erste Nachricht ist
`knoten.anmelden`; danach Messwerte im Takt, die Dienstliste bei Änderung und Antworten auf Befehle.
Installationsskript und Paket gibt es nur aus erlaubten Netzen; das Skript enthält keinen Schlüssel.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import tarfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response
from pydantic import ValidationError

from .. import version
from ..fach.betrieb import Betrieb
from ..protokoll.knoten import BefehlErgebnis, Dienstliste, KnotenAnmeldung, Messwerte
from ..protokoll.umschlag import Umschlag, umschlag

router = APIRouter()
log = logging.getLogger("leitstelle.agent")
PAKET_AUSLASSEN = {"__pycache__", ".venv", ".pytest_cache", "tests"}


def _schluessel(kopf: str | None) -> str | None:
    if kopf and kopf.lower().startswith("bearer "):
        return kopf[7:].strip() or None
    return None


@router.websocket("/agent/kanal")
async def kanal(ws: WebSocket) -> None:
    betrieb: Betrieb = ws.app.state.betrieb
    knoten = betrieb.knoten_zum_agentschluessel(_schluessel(ws.headers.get("authorization")) or "")
    await ws.accept()                       # erst annehmen, damit der Agent das Grundwort lesen kann
    if knoten is None:
        await ws.close(code=4401, reason="unbekannter_schluessel")
        return
    sperre = asyncio.Lock()

    async def senden(u: Umschlag) -> None:
        async with sperre:
            await ws.send_text(u.model_dump_json())

    async def beenden() -> None:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await ws.close(code=4401, reason="schluessel_erneuert")

    try:
        erste = Umschlag.model_validate_json(await asyncio.wait_for(ws.receive_text(), timeout=betrieb.konfig.verbindung_s))
        if erste.art != "knoten.anmelden":
            await ws.close(code=4400, reason="erst knoten.anmelden")
            return
        anmeldung = KnotenAnmeldung.model_validate(erste.nutzlast)
    except (TimeoutError, ValidationError, WebSocketDisconnect):
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await ws.close(code=4400, reason="anmeldung_fehlt")
        return

    alt = betrieb.agenten.verbindung(knoten.kennung)
    if alt and alt.beenden:
        await alt.beenden()
    v = betrieb.agenten.anmelden(knoten.kennung, anmeldung, senden, betrieb.uhr.jetzt(), beenden)
    await senden(umschlag("knoten.angemeldet", {"knoten": knoten.kennung, "name": knoten.name}, an=f"agent:{knoten.kennung}", bezug=erste.id))
    betrieb.agent_angemeldet(v)
    try:
        while True:
            u = Umschlag.model_validate_json(await ws.receive_text())
            if betrieb.agenten.verbindung(knoten.kennung) is not v:
                break                                   # inzwischen durch eine neuere Verbindung ersetzt
            try:
                match u.art:
                    case "knoten.messwerte":
                        v.messwerte, v.messzeit_s = Messwerte.model_validate(u.nutzlast), betrieb.uhr.jetzt()
                        betrieb.messwerte_uebernehmen(v)
                    case "knoten.dienste":
                        v.dienste = Dienstliste.model_validate(u.nutzlast)
                        await betrieb.agent_dienste(v)
                    case "knoten.befehl_ergebnis":
                        betrieb.agenten.ergebnis(v, u.bezug, BefehlErgebnis.model_validate(u.nutzlast))
                    case "herzschlag":
                        pass
                    case _:
                        log.warning("Unbekannte Nachricht vom Agenten auf %s: %s", knoten.name, u.art)
            except ValidationError as f:
                log.warning("Ungültige Nachricht %s vom Agenten auf %s: %s", u.art, knoten.name, f.errors()[:2])
    except (WebSocketDisconnect, RuntimeError, ValidationError):
        pass
    finally:
        if betrieb.agenten.abmelden(v):
            betrieb.agent_getrennt(knoten.kennung)


def _erlaubt(request: Request) -> None:
    if not request.app.state.konfig.erlaubt(request.client.host if request.client else None):
        raise HTTPException(403, {"grund": "herkunft_nicht_erlaubt", "begruendung": "Nur aus dem Heimnetz oder über VPN erreichbar."})


def _quelle(request: Request) -> Path:
    quelle = request.app.state.konfig.agent_quelle
    if quelle is None or not (quelle / "pyproject.toml").exists():
        raise HTTPException(404, {"grund": "unbekannt", "begruendung": "Diese Leitstelle liefert den Agenten nicht aus."})
    return quelle


@router.get("/agent/installieren.sh", include_in_schema=False)
async def installieren(request: Request) -> PlainTextResponse:
    """Installationsskript mit der Adresse dieser Leitstelle; der Schlüssel wird beim Ausführen erfragt."""
    _erlaubt(request)
    skript = (_quelle(request) / "installieren.sh").read_text(encoding="utf-8")
    basis = str(request.base_url).rstrip("/")
    return PlainTextResponse(skript.replace("__LEITSTELLE_ADRESSE__", basis), headers={"Cache-Control": "no-cache"})


@router.get("/agent/paket.tar.gz", include_in_schema=False)
async def paket(request: Request) -> Response:
    _erlaubt(request)
    quelle = _quelle(request)
    puffer = io.BytesIO()
    fassung = version().encode()
    with tarfile.open(fileobj=puffer, mode="w:gz") as tar:
        tar.add(quelle, arcname="leitstelle-agent",
                filter=lambda t: None if Path(t.name).name in PAKET_AUSLASSEN or t.name.endswith(".egg-info") else t)
        eintrag = tarfile.TarInfo("leitstelle-agent/leitstelle_agent/VERSION")
        eintrag.size = len(fassung)
        tar.addfile(eintrag, io.BytesIO(fassung))
    return Response(puffer.getvalue(), media_type="application/gzip", headers={"Cache-Control": "no-cache"})
