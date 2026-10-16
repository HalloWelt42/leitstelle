"""Knoten-Agenten: Kanal `/agent/kanal` (WebSocket).

Ein Knoten-Agent (zum Beispiel der Maschinenraum eines Rechners) verbindet sich von sich aus mit seinem
Schlüssel als Bearer. Erste Nachricht ist `knoten.anmelden`; danach Messwerte im Takt, die Dienstliste bei
Änderung und Antworten auf Befehle.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..fach.betrieb import Betrieb
from ..protokoll.knoten import BefehlErgebnis, Dienstliste, KnotenAnmeldung, Messwerte
from ..protokoll.umschlag import Umschlag, umschlag

router = APIRouter()
log = logging.getLogger("leitstelle.agent")


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

