"""Fassade im OpenAI-Format: Anwendungen ohne Umbau, dauerhaft verträglich (PROTOKOLL.md Abschnitt 6).

Basisadresse mit oder ohne `/v1`. Schlüssel als Bearer. Wartet ein Auftrag, kommen in Strömen alle
`hinweis_s` Kommentarzeilen, die jeder SSE-Leser überliest; Köpfe `X-Leitstelle-*` tragen Auftrag,
Lage und geschätzte Wartezeit. Nachgebildet werden auch die Modelllisten des Läufers, weil mehrere
Anwendungen genau diese Form lesen.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ..fach.fehler import Ablehnung
from ..fach.vermittlung import Vorgang, Wartet
from ..kern.werte import GIB, WORT, Auftragszustand, Faehigkeit, Modellzustand, Prioritaet, Zone
from ..ports.ablage.eintraege import AnwendungEintrag
from ..ports.dienste import Durchleitung
from .gemeinsam import betrieb, fehler_antwort, konfig, vermittlung

router = APIRouter()

PRIORITAET_WORT = {"hintergrund": Prioritaet.HINTERGRUND, "normal": Prioritaet.NORMAL, "hoch": Prioritaet.HOCH, "dringend": Prioritaet.DRINGEND}


def _anwendung(request: Request) -> AnwendungEintrag | None:
    kopf = request.headers.get("authorization", "")
    if not kopf.lower().startswith("bearer "):
        return None
    return betrieb(request).anwendung_zum_schluessel(kopf[7:].strip())


def _prioritaet(request: Request, app: AnwendungEintrag) -> Prioritaet:
    """Kopf X-Leitstelle-Prioritaet darf absenken, nie über die Vorgabe der Anwendung heben."""
    wunsch = PRIORITAET_WORT.get(request.headers.get("x-leitstelle-prioritaet", "").strip().lower())
    return min(wunsch, app.prioritaet) if wunsch is not None else app.prioritaet


def _titel(request: Request, faehigkeit: Faehigkeit) -> str:
    """X-Leitstelle-Titel: HTTP-Köpfe tragen nur ASCII; Umlaute kommen prozentkodiert (ANBINDUNG 2.1).
    Schickt eine Anwendung doch rohe UTF-8-Bytes, werden sie repariert."""
    roh = request.headers.get("x-leitstelle-titel", "").strip()
    try:
        roh = roh.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return unquote(roh)[:200] or f"{WORT[faehigkeit.value]} über die Fassade"


def _bild_im_chat(koerper: dict[str, Any]) -> bool:
    for n in koerper.get("messages") or []:
        inhalt = n.get("content") if isinstance(n, dict) else None
        if isinstance(inhalt, list) and any(isinstance(t, dict) and t.get("type") in ("image_url", "input_image", "image") for t in inhalt):
            return True
    return False


def _kopf(request: Request, v: Vorgang) -> dict[str, str]:
    b = betrieb(request)
    kopf = {"X-Leitstelle-Auftrag": v.auftrag.kennung, "X-Leitstelle-Lage": b.kern.lage.value}
    if v.auftrag.wartet and v.auftrag.voraussichtlich_s is not None:
        kopf["X-Leitstelle-Wartet-S"] = str(round(v.auftrag.voraussichtlich_s))
    return kopf


def _hinweis(w: Wartet) -> bytes:
    zusatz = f", etwa {w.voraussichtlich_s:.0f} s" if w.voraussichtlich_s is not None else ""
    return f": wartet, {w.begruendung}{zusatz}\n\n".encode()


async def _vermitteln(request: Request, pfad: str, faehigkeit: Faehigkeit) -> Response:
    app = _anwendung(request)
    if app is None:
        return fehler_antwort("unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt (Kopf Authorization: Bearer ...).")
    try:
        koerper = await request.json()
    except ValueError:
        return JSONResponse({"error": {"message": "Der Körper ist kein JSON.", "type": "leitstelle", "code": "eingabe"}}, status_code=400)
    if faehigkeit == Faehigkeit.TEXT and _bild_im_chat(koerper):
        faehigkeit = Faehigkeit.BILD_BESCHREIBEN
    strom = bool(koerper.get("stream")) and faehigkeit != Faehigkeit.EINBETTUNG
    titel = _titel(request, faehigkeit)
    verm = vermittlung(request)
    try:
        v = verm.annehmen(app.kennung, faehigkeit, koerper.get("model"), _prioritaet(request, app), titel)
    except Ablehnung as a:
        return fehler_antwort(a.grund, a.begruendung)

    if strom:
        async def sse():
            try:
                async for teil in verm.ausfuehren(v, pfad, koerper, True):
                    yield _hinweis(teil) if isinstance(teil, Wartet) else teil
            except Ablehnung as a:
                daten = json.dumps({"error": {"message": a.begruendung, "type": "leitstelle", "code": a.grund}}, ensure_ascii=False)
                yield f"data: {daten}\n\ndata: [DONE]\n\n".encode()
            finally:
                verm.aufraeumen(v)

        return StreamingResponse(sse(), media_type="text/event-stream", headers={**_kopf(request, v), "Cache-Control": "no-cache"})

    teile: list[bytes] = []
    try:
        async for teil in verm.ausfuehren(v, pfad, koerper, False, getrennt=request.is_disconnected):
            if not isinstance(teil, Wartet):
                teile.append(teil)
    except Ablehnung as a:
        return fehler_antwort(a.grund, a.begruendung)
    finally:
        verm.aufraeumen(v)
    kopf = _kopf(request, v) | {"X-Leitstelle-Modell": v.modellname} | ({"X-Leitstelle-Knoten": v.knoten} if v.knoten else {})
    z = v.auftrag.zustand
    if z == Auftragszustand.FERTIG:
        return Response(b"".join(teile), media_type="application/json", headers=kopf)
    grund = v.auftrag.grund or ("dienst_fehler" if z == Auftragszustand.FEHLGESCHLAGEN else "nutzer")
    antwort = fehler_antwort(grund, v.auftrag.begruendung or "abgebrochen")
    antwort.headers.update(kopf)
    return antwort


async def chat(request: Request) -> Response:
    return await _vermitteln(request, "/v1/chat/completions", Faehigkeit.TEXT)


async def einbettung(request: Request) -> Response:
    return await _vermitteln(request, "/v1/embeddings", Faehigkeit.EINBETTUNG)


# Köpfe, die nur einer Verbindung gelten oder die Leitstelle selbst auswertet
OHNE_KOPF = {"host", "authorization", "content-length", "connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
             "x-leitstelle-titel", "x-leitstelle-prioritaet"}


async def dienst(request: Request, name: str, pfad: str) -> Response:
    """Jeder Dienst mit eigener Schnittstelle (Sprache, Bild, Musik): `/v1/dienste/<name>/<pfad>` wird ein Auftrag. Die
    Leitstelle prüft die Rechte, startet den Dienst bei Bedarf, plant seinen Speicher ein und reicht Anfrage und Antwort
    unverändert durch. So geht jeder Zugriff über die Leitstelle, auch zu Diensten, die nur auf ihrem Rechner lauschen."""
    app = _anwendung(request)
    if app is None:
        return fehler_antwort("unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt (Kopf Authorization: Bearer ...).")
    b, verm = betrieb(request), vermittlung(request)
    familie = b.familie_fuer(name)
    if familie is None:
        a = b.unbekannt(name, "Dienst")
        return fehler_antwort(a.grund, a.begruendung)
    try:
        faehigkeit = verm.faehigkeit_fuer(app.kennung, familie)
        v = verm.annehmen(app.kennung, faehigkeit, name, _prioritaet(request, app), _titel(request, faehigkeit))
    except Ablehnung as a:
        return fehler_antwort(a.grund, a.begruendung)
    anfrage = Durchleitung(methode=request.method, pfad=pfad, abfrage=request.url.query, inhalt=await request.body(),
                           kopf={k: w for k, w in request.headers.items() if k.lower() not in OHNE_KOPF})
    try:
        async for _ in verm.warten(v, getrennt=request.is_disconnected):
            pass
        antwort = await verm.roh_anfragen(v, anfrage)
    except Ablehnung as a:
        verm.aufraeumen(v)
        fehler = fehler_antwort(a.grund, a.begruendung)
        fehler.headers.update(_kopf(request, v))
        return fehler
    kopf = {k: w for k, w in antwort.kopf.items() if k.lower() not in OHNE_KOPF} | _kopf(request, v) | {"X-Leitstelle-Modell": v.modellname}
    if v.knoten:
        kopf["X-Leitstelle-Knoten"] = v.knoten
    return StreamingResponse(verm.roh_strom(v, antwort), status_code=antwort.status, headers=kopf)


router.add_api_route("/v1/dienste/{name}/{pfad:path}", dienst, methods=["GET", "POST", "PUT", "PATCH", "DELETE"], name="dienst")

for basis in ("/v1", ""):     # Basisadresse mit oder ohne /v1
    router.add_api_route(f"{basis}/chat/completions", chat, methods=["POST"], include_in_schema=basis == "/v1", name=f"chat{basis or '_ohne_v1'}")
    router.add_api_route(f"{basis}/embeddings", einbettung, methods=["POST"], include_in_schema=basis == "/v1", name=f"einbettung{basis or '_ohne_v1'}")


def _sichtbare_modelle(request: Request, app: AnwendungEintrag | None):
    """Modelle, die die Anwendung nutzen darf (Fähigkeit und Zone); ohne Schlüssel aus dem Heimnetz alle."""
    b = betrieb(request)
    gesehen: dict[str, Any] = {}
    for m in b.verbund.modelle.values():
        d = b.verbund.dienste.get(m.dienst)
        if d is None:
            continue
        if app is not None:
            if not (m.faehigkeiten & app.faehigkeiten):
                continue
            zone = Zone.EXTERN if d.extern else (b.verbund.knoten[d.knoten].zone if d.knoten in b.verbund.knoten else None)
            if zone not in app.zonen:
                continue
        bisher = gesehen.get(m.familie)
        if bisher is None or (m.zustand != Modellzustand.FREI and bisher.zustand == Modellzustand.FREI):
            gesehen[m.familie] = m
    return list(gesehen.values())


def _darf_lesen(request: Request) -> tuple[bool, AnwendungEintrag | None]:
    app = _anwendung(request)
    if app is not None:
        return True, app
    return konfig(request).erlaubt(request.client.host if request.client else None) and not request.headers.get("authorization"), None


@router.get("/v1/models")
@router.get("/models", include_in_schema=False)
async def modelle(request: Request):
    darf, app = _darf_lesen(request)
    if not darf:
        return fehler_antwort("unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt.")
    b = betrieb(request)
    daten = []
    for m in _sichtbare_modelle(request, app):
        d = b.verbund.dienste[m.dienst]
        daten.append({"id": m.familie, "object": "model", "owned_by": "leitstelle",
                      "x-leitstelle": {"name": m.name, "geladen": m.zustand != Modellzustand.FREI, "knoten": d.knoten, "extern": d.extern,
                                       "faehigkeiten": sorted(f.value for f in m.faehigkeiten), "gb": m.gb}})
    return {"object": "list", "data": daten}


def _typ(m) -> str:
    if Faehigkeit.EINBETTUNG in m.faehigkeiten:
        return "embeddings"
    return "vlm" if Faehigkeit.BILD_BESCHREIBEN in m.faehigkeiten else "llm"


@router.get("/api/v0/models", include_in_schema=False)
async def modelle_v0(request: Request):
    darf, app = _darf_lesen(request)
    if not darf:
        return fehler_antwort("unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt.")
    b = betrieb(request)
    return {"object": "list", "data": [{"id": m.familie, "object": "model", "type": _typ(m), "publisher": m.familie.split("/")[0] if "/" in m.familie else "",
                                        "state": "loaded" if m.zustand != Modellzustand.FREI else "not-loaded",
                                        "max_context_length": b.ort(m.kennung).kontext} for m in _sichtbare_modelle(request, app)]}


@router.get("/api/v1/models", include_in_schema=False)
async def modelle_v1(request: Request):
    darf, app = _darf_lesen(request)
    if not darf:
        return fehler_antwort("unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt.")
    b = betrieb(request)
    aus = []
    for m in _sichtbare_modelle(request, app):
        ort = b.ort(m.kennung)
        geladen = m.zustand != Modellzustand.FREI
        aus.append({"key": m.familie, "type": "embedding" if _typ(m) == "embeddings" else "llm", "display_name": m.name,
                    "params_string": f"{m.parameter_mrd:g}B" if m.parameter_mrd else None, "size_bytes": int(m.gb * GIB),
                    "max_context_length": ort.kontext, "capabilities": {"vision": Faehigkeit.BILD_BESCHREIBEN in m.faehigkeiten,
                                                                         "trained_for_tool_use": Faehigkeit.WERKZEUG in m.faehigkeiten},
                    "loaded_instances": [{"id": ort.anfragename}] if geladen else []})
    return {"models": aus}
