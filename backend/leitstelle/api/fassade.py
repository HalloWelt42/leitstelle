"""Fassade im OpenAI-Format: Anwendungen ohne Umbau, dauerhaft verträglich (PROTOKOLL.md Abschnitt 6).

Basisadresse mit oder ohne `/v1`. Schlüssel als Bearer. Wartet ein Auftrag, kommen in Strömen alle
`hinweis_s` Kommentarzeilen, die jeder SSE-Leser überliest; Köpfe `X-Leitstelle-*` tragen Auftrag,
Lage und geschätzte Wartezeit. Nachgebildet werden auch die Modelllisten des Läufers, weil mehrere
Anwendungen genau diese Form lesen.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError

from ..fach.fehler import Ablehnung, fehler_inhalt
from ..fach.vermittlung import Bilderzeugung, Vorgang, Wartet
from ..kern.modelle import Modell
from ..kern.werte import GIB, WORT, Auftragszustand, Dienstzustand, Eignung, Faehigkeit, Modellzustand, Prioritaet, Zone
from ..ports.ablage.eintraege import Adapterart
from ..ports.ablage.eintraege import AnwendungEintrag
from ..ports.dienste import Durchleitung
from ..ports.dienste.bilder import Bildauftrag
from ..protokoll.fassade import Bereitschaft, BildAnfrage, BildAntwort, BildDaten, BildZusatz, DienstListe, DienstSicht
from .gemeinsam import ablehnung_antwort, betrieb, fehler_antwort, konfig, vermittlung

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


ARBEIT_ZEICHEN = re.compile(r"[A-Za-z0-9._:-]{1,64}")


def _arbeit(request: Request) -> str | None:
    """X-Leitstelle-Arbeit: Kennung der Arbeit, zu der die Anfrage gehört (ANBINDUNG 2.1); nur erlaubte Zeichen, sonst
    zählt die Anfrage für sich."""
    roh = request.headers.get("x-leitstelle-arbeit", "").strip()
    return roh if ARBEIT_ZEICHEN.fullmatch(roh) else None


def _extern(request: Request) -> list[str]:
    """X-Leitstelle-Extern: Erlaubnisliste der App für externe Modelle, durch Komma getrennt (prozentkodiert wie der Titel).
    Ohne Kopf oder leer: die Anfrage geht nicht nach extern, außer die App verlangt ein externes Modell ausdrücklich."""
    roh = unquote(request.headers.get("x-leitstelle-extern", ""))
    b = betrieb(request)
    return sorted({f for name in roh.split(",") if name.strip() and (f := b.familie_fuer(name.strip()))})


def _instanz(request: Request, familie: str) -> str | None:
    """X-Leitstelle-Instanz: ein Folgeaufruf (Ergebnis abholen) an dieselbe Instanz wie der erste; nur eine Instanz
    dieser Familie zählt, sonst gilt der Kopf nicht."""
    roh = request.headers.get("x-leitstelle-instanz", "").strip()[:200]
    if not roh:
        return None
    m = betrieb(request).verbund.modelle.get(roh)
    if m is None:
        return roh                    # läuft nicht mehr: der Zuteiler lehnt mit "instanz_weg" ab, statt woanders zu suchen
    return roh if m.familie == familie else None


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
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt (Kopf Authorization: Bearer ...).")
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
        v = verm.annehmen(app.kennung, faehigkeit, koerper.get("model"), _prioritaet(request, app), titel, _arbeit(request), _extern(request), koerper=koerper)
    except Ablehnung as a:
        return ablehnung_antwort(request, a)

    if strom:
        async def sse():
            try:
                async for teil in verm.ausfuehren(v, pfad, koerper, True):
                    yield _hinweis(teil) if isinstance(teil, Wartet) else teil
            except Ablehnung as a:
                daten = json.dumps({"error": fehler_inhalt(a.grund, a.begruendung, a.zusatz)}, ensure_ascii=False)
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
        return ablehnung_antwort(request, a)
    finally:
        verm.aufraeumen(v)
    kopf = _kopf(request, v) | {"X-Leitstelle-Modell": v.modellname} | ({"X-Leitstelle-Knoten": v.knoten} if v.knoten else {})
    z = v.auftrag.zustand
    if z == Auftragszustand.FERTIG:
        return Response(b"".join(teile), media_type="application/json", headers=kopf)
    grund = v.auftrag.grund or ("dienst_fehler" if z == Auftragszustand.FEHLGESCHLAGEN else "nutzer")
    antwort = fehler_antwort(request, grund, v.auftrag.begruendung or "abgebrochen", v.lauf.zusatz)
    antwort.headers.update(kopf)
    return antwort


async def chat(request: Request) -> Response:
    return await _vermitteln(request, "/v1/chat/completions", Faehigkeit.TEXT)


async def einbettung(request: Request) -> Response:
    return await _vermitteln(request, "/v1/embeddings", Faehigkeit.EINBETTUNG)


def _eingabefehler(text: str) -> JSONResponse:
    return JSONResponse({"error": {"message": text, "type": "leitstelle", "code": "eingabe"}}, status_code=400)


def _eingabe_text(fehler: ValidationError) -> str:
    """Prüffehler der Anfrage auf Deutsch, je Feld ein Satz."""
    saetze = []
    for f in fehler.errors():
        feld = ".".join(str(x) for x in f["loc"]) or "Körper"
        if f["type"] == "value_error":
            saetze.append(str(f["ctx"]["error"]))
        elif f["type"] == "missing":
            saetze.append(f"{feld} fehlt.")
        elif f["type"] in ("greater_than", "greater_than_equal", "less_than", "less_than_equal", "string_too_short", "string_too_long"):
            grenzen = ", ".join(f"{k} {w}" for k, w in (f.get("ctx") or {}).items())
            saetze.append(f"{feld} liegt außerhalb der Grenzen ({grenzen}).")
        else:
            saetze.append(f"{feld} hat nicht die erwartete Form.")
    return " ".join(saetze)


def _bildantwort(request: Request, e: Bilderzeugung) -> bytes:
    antwort = BildAntwort(created=int(betrieb(request).uhr.jetzt()), data=[BildDaten(b64_json=base64.b64encode(b).decode("ascii")) for b in e.ergebnis.bilder],
                          x_leitstelle=BildZusatz(seed=e.ergebnis.seed, modell=e.familie, dauer_ms=round(e.dauer_s * 1000)))
    return json.dumps(antwort.model_dump(mode="json", by_alias=True), ensure_ascii=False).encode()


async def bilder(request: Request) -> Response:
    """Bilder erzeugen im OpenAI-Format (PROTOKOLL 6): ein Auftrag mit der Fähigkeit bild_erzeugen. Den Ablauf des
    Bilddienstes kennt nur sein Bildablauf; die Anwendung nennt Beschreibung, Größe, Anzahl und wahlweise Startwert."""
    app = _anwendung(request)
    if app is None:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt (Kopf Authorization: Bearer ...).")
    try:
        anfrage = BildAnfrage.model_validate(await request.json())
    except ValueError as fehler:
        return _eingabefehler(_eingabe_text(fehler) if isinstance(fehler, ValidationError) else "Der Körper ist kein JSON.")
    b, verm = betrieb(request), vermittlung(request)
    try:
        if anfrage.model and (familie := b.familie_fuer(anfrage.model)):
            verm.bildablauf_fuer(familie)            # ohne Bildablauf gar nicht erst einreihen (und keinen Dienst starten)
        v = verm.annehmen(app.kennung, Faehigkeit.BILD_ERZEUGEN, anfrage.model, _prioritaet(request, app), _titel(request, Faehigkeit.BILD_ERZEUGEN),
                          _arbeit(request), _extern(request))
    except Ablehnung as a:
        return ablehnung_antwort(request, a)
    auftrag = Bildauftrag(beschreibung=anfrage.prompt, breite=anfrage.breite, hoehe=anfrage.hoehe, anzahl=anfrage.n, seed=verm.startwert(anfrage.seed))
    if anfrage.stream:
        return StreamingResponse(_bilder_strom(request, v, auftrag), media_type="text/event-stream", headers={**_kopf(request, v), "Cache-Control": "no-cache"})
    try:
        async for _ in verm.warten(v, getrennt=request.is_disconnected):
            pass
        erzeugung = await verm.bilder_erzeugen(v, auftrag)
    except Ablehnung as a:
        antwort = ablehnung_antwort(request, a)
        antwort.headers.update(_kopf(request, v))
        return antwort
    finally:
        verm.aufraeumen(v)
    kopf = _kopf(request, v) | {"X-Leitstelle-Modell": v.modellname} | ({"X-Leitstelle-Knoten": v.knoten} if v.knoten else {})
    return Response(_bildantwort(request, erzeugung), media_type="application/json", headers=kopf)


async def _bilder_strom(request: Request, v: Vorgang, auftrag: Bildauftrag):
    """Wie der Chat: Kommentare, solange der Auftrag wartet, und während der Dienst rechnet, damit die Verbindung offen
    bleibt; dann genau ein `data:` mit der Antwort (oder dem Fehler) und `data: [DONE]`. Geht die Anwendung, endet der
    Auftrag, und der Bilddienst nimmt ihn aus seiner Warteschlange."""
    verm = vermittlung(request)
    arbeit: asyncio.Future[Bilderzeugung] | None = None
    try:
        async for w in verm.warten(v):
            yield _hinweis(w)
        arbeit = asyncio.ensure_future(verm.bilder_erzeugen(v, auftrag))
        seit = 0.0
        while not (await asyncio.wait({arbeit}, timeout=konfig(request).hinweis_s))[0]:
            seit += konfig(request).hinweis_s
            yield f": rechnet seit {seit:.0f} s\n\n".encode()
        yield b"data: " + _bildantwort(request, arbeit.result()) + b"\n\ndata: [DONE]\n\n"
    except Ablehnung as a:
        daten = json.dumps({"error": fehler_inhalt(a.grund, a.begruendung, a.zusatz)}, ensure_ascii=False)
        yield f"data: {daten}\n\ndata: [DONE]\n\n".encode()
    finally:
        # ohne `await`: reißt die Anwendung ab, wird dieser Rest abgebrochen; der Auftrag braucht seinen Endzustand trotzdem
        if arbeit is not None and not arbeit.done():
            v.lauf.beenden_mit("anwendung", "Die Anwendung hat die Verbindung getrennt.")
        verm.aufraeumen(v)


# Köpfe, die nur einer Verbindung gelten oder die Leitstelle selbst auswertet
OHNE_KOPF = {"host", "authorization", "content-length", "connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
             "x-leitstelle-titel", "x-leitstelle-prioritaet", "x-leitstelle-arbeit", "x-leitstelle-extern", "x-leitstelle-instanz"}


async def dienst(request: Request, name: str, pfad: str) -> Response:
    """Jeder Dienst mit eigener Schnittstelle (Sprache, Bild, Musik): `/v1/dienste/<name>/<pfad>` wird ein Auftrag. Die
    Leitstelle prüft die Rechte, startet den Dienst bei Bedarf, plant seinen Speicher ein und reicht Anfrage und Antwort
    unverändert durch. So geht jeder Zugriff über die Leitstelle, auch zu Diensten, die nur auf ihrem Rechner lauschen."""
    app = _anwendung(request)
    if app is None:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt (Kopf Authorization: Bearer ...).")
    b, verm = betrieb(request), vermittlung(request)
    familie = b.familie_fuer(name)
    if familie is None:
        return ablehnung_antwort(request, b.unbekannt(name, "Dienst"))
    try:
        faehigkeit = verm.faehigkeit_fuer(app.kennung, familie)
        v = verm.annehmen(app.kennung, faehigkeit, name, _prioritaet(request, app), _titel(request, faehigkeit), _arbeit(request), _extern(request),
                          instanz=_instanz(request, familie))
    except Ablehnung as a:
        return ablehnung_antwort(request, a)
    anfrage = Durchleitung(methode=request.method, pfad=pfad, abfrage=request.url.query, inhalt=await request.body(),
                           kopf={k: w for k, w in request.headers.items() if k.lower() not in OHNE_KOPF})
    try:
        async for _ in verm.warten(v, getrennt=request.is_disconnected):
            pass
        antwort = await verm.roh_anfragen(v, anfrage)
    except Ablehnung as a:
        verm.aufraeumen(v)
        fehler = ablehnung_antwort(request, a)
        fehler.headers.update(_kopf(request, v))
        return fehler
    kopf = {k: w for k, w in antwort.kopf.items() if k.lower() not in OHNE_KOPF} | _kopf(request, v) | {"X-Leitstelle-Modell": v.modellname}
    if v.auftrag.modell:
        kopf["X-Leitstelle-Instanz"] = v.auftrag.modell       # für Folgeaufrufe an dieselbe Instanz (Bindung)
    if v.knoten:
        kopf["X-Leitstelle-Knoten"] = v.knoten
    return StreamingResponse(verm.roh_strom(v, antwort), status_code=antwort.status, headers=kopf)


router.add_api_route("/v1/dienste/{name}/{pfad:path}", dienst, methods=["GET", "POST", "PUT", "PATCH", "DELETE"], name="dienst")

for basis in ("/v1", ""):     # Basisadresse mit oder ohne /v1
    router.add_api_route(f"{basis}/chat/completions", chat, methods=["POST"], include_in_schema=basis == "/v1", name=f"chat{basis or '_ohne_v1'}")
    router.add_api_route(f"{basis}/embeddings", einbettung, methods=["POST"], include_in_schema=basis == "/v1", name=f"einbettung{basis or '_ohne_v1'}")
    router.add_api_route(f"{basis}/images/generations", bilder, methods=["POST"], include_in_schema=basis == "/v1", name=f"bilder{basis or '_ohne_v1'}")


def _erlaubte_modelle(request: Request, app: AnwendungEintrag | None) -> list[Modell]:
    """Alle Modellinstanzen, die die Anwendung nutzen darf (Fähigkeit und Zone); ohne Schlüssel aus dem Heimnetz alle."""
    b = betrieb(request)
    aus = []
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
        aus.append(m)
    return aus


def _sichtbare_modelle(request: Request, app: AnwendungEintrag | None) -> list[Modell]:
    """Je Familie eine Instanz der erlaubten Modelle, geladene vor freien."""
    gesehen: dict[str, Modell] = {}
    for m in _erlaubte_modelle(request, app):
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
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt.")
    b = betrieb(request)
    daten = []
    for m in _sichtbare_modelle(request, app):
        d = b.verbund.dienste[m.dienst]
        daten.append({"id": m.familie, "object": "model", "owned_by": "leitstelle",
                      "x-leitstelle": {"name": m.name, "geladen": m.zustand != Modellzustand.FREI, "knoten": d.knoten, "extern": d.extern,
                                       "knoten_name": b.verbund.knoten[d.knoten].name if d.knoten in b.verbund.knoten else None,
                                       "faehigkeiten": sorted(f.value for f in m.faehigkeiten), "gb": m.gb,
                                       "steckbrief": b.steckbrief(m).model_dump(mode="json")}})
    return {"object": "list", "data": daten}


@router.get("/v1/steckbriefe")
async def steckbriefe(request: Request, faehigkeit: Faehigkeit | None = None, eignung: Eignung | None = None, sprache: str | None = None):
    """Wofür welches Modell gemacht ist (PROTOKOLL 4.8), nur Modelle, die die Anwendung nutzen darf. Filter: Fähigkeit und
    Eignung müssen passen; bei `sprache` zuerst die Modelle, die sie ausdrücklich können, dann die ohne Angabe."""
    darf, app = _darf_lesen(request)
    if not darf:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt.")
    b = betrieb(request)
    aus = []
    for m in _sichtbare_modelle(request, app):
        s = b.steckbrief(m)
        if (faehigkeit and faehigkeit not in s.faehigkeiten) or (eignung and eignung not in s.eignung) or (sprache and s.sprachen and sprache not in s.sprachen):
            continue
        aus.append((0 if sprache and sprache in s.sprachen else 1, m.zustand == Modellzustand.FREI, m.name.lower(),
                    {"id": m.familie, "name": m.name, "geladen": m.zustand != Modellzustand.FREI, "steckbrief": s.model_dump(mode="json")}))
    return {"object": "list", "data": [x[3] for x in sorted(aus, key=lambda x: x[:3])]}


# Fasst die Instanzen eines Dienstes zusammen: der beste Zustand zählt (eine laufende Instanz genügt)
BEREITSCHAFT_VORRANG = [Bereitschaft.BEREIT, Bereitschaft.STARTET, Bereitschaft.AUS, Bereitschaft.SCHLAEFT, Bereitschaft.NICHT_ERREICHBAR]
MODELL_BEREITSCHAFT = {Modellzustand.GELADEN: Bereitschaft.BEREIT, Modellzustand.RECHNET: Bereitschaft.BEREIT,
                       Modellzustand.LAEDT: Bereitschaft.STARTET, Modellzustand.FREI: Bereitschaft.AUS}


def _bereitschaft(request: Request, m: Modell) -> Bereitschaft:
    v = betrieb(request).verbund
    d = v.dienste[m.dienst]
    if d.zustand == Dienstzustand.SCHLAEFT or v.auf_schlafendem(d.kennung):
        return Bereitschaft.SCHLAEFT
    if d.zustand in (Dienstzustand.NICHT_ERREICHBAR, Dienstzustand.AUSFALL):
        return Bereitschaft.NICHT_ERREICHBAR
    return MODELL_BEREITSCHAFT[m.zustand]


@router.get("/v1/dienste")
async def dienste(request: Request):
    """Die Dienste im Maschinenraum, die die Anwendung nutzen darf (PROTOKOLL 6): Kennung, Name, Fähigkeiten, Zustand,
    Rechner; je Dienst ein Eintrag, gleich wie viele Instanzen auf wie vielen Rechnern laufen."""
    darf, app = _darf_lesen(request)
    if not darf:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt.")
    b = betrieb(request)
    gruppen: dict[str, list[Modell]] = {}
    for m in _erlaubte_modelle(request, app):
        if b.verbund.dienste[m.dienst].art == Adapterart.AGENT.value:
            gruppen.setdefault(m.familie, []).append(m)
    aus = []
    for familie, instanzen in sorted(gruppen.items()):
        grund = next((m for m in instanzen if not m.zusatz), instanzen[0])
        knoten = {b.verbund.dienste[m.dienst].knoten for m in instanzen}
        faehig = set().union(*(m.faehigkeiten for m in instanzen)) & (app.faehigkeiten if app else set(Faehigkeit))
        aus.append(DienstSicht(kennung=familie, name=grund.name, faehigkeiten=[f for f in Faehigkeit if f in faehig],
                               zustand=min((_bereitschaft(request, m) for m in instanzen), key=BEREITSCHAFT_VORRANG.index),
                               rechner=sorted(b.verbund.knoten[k].name for k in knoten if k in b.verbund.knoten)))
    return DienstListe(data=aus).model_dump(mode="json")


def _typ(m) -> str:
    if Faehigkeit.EINBETTUNG in m.faehigkeiten:
        return "embeddings"
    return "vlm" if Faehigkeit.BILD_BESCHREIBEN in m.faehigkeiten else "llm"


@router.get("/api/v0/models", include_in_schema=False)
async def modelle_v0(request: Request):
    darf, app = _darf_lesen(request)
    if not darf:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt.")
    b = betrieb(request)
    return {"object": "list", "data": [{"id": m.familie, "object": "model", "type": _typ(m), "publisher": m.familie.split("/")[0] if "/" in m.familie else "",
                                        "state": "loaded" if m.zustand != Modellzustand.FREI else "not-loaded",
                                        "max_context_length": b.ort(m.kennung).kontext} for m in _sichtbare_modelle(request, app)]}


@router.get("/api/v1/models", include_in_schema=False)
async def modelle_v1(request: Request):
    darf, app = _darf_lesen(request)
    if not darf:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt.")
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
