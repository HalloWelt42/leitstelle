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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError

from ..fach.auskunft import einschaetzung, lageauskunft
from ..fach.bildablage import ist_archiv
from ..fach.einordnen import einordnen
from ..fach.fehler import Ablehnung, fehler_inhalt
from ..fach.vermittlung import Bilderzeugung, Vorgang, Wartet
from ..kern.modelle import Modell
from ..kern.werte import GIB, WORT, Auftragsart, Auftragszustand, Dienstzustand, Eignung, Faehigkeit, Modellzustand, Prioritaet, Zone
from ..ports.ablage.eintraege import Adapterart
from ..ports.ablage.eintraege import AnwendungEintrag
from ..ports.dienste import Durchleitung
from ..protokoll.fassade import (Bereitschaft, BildAnfrage, BildAntwort, BildDaten, BildZusatz, DienstListe, DienstSicht, Einordnung,
                                 Einordnungsanfrage, Einschaetzungsanfrage, Modellwahl, RechnerOrt)
from .gemeinsam import ablehnung_antwort, betrieb, fehler_antwort, konfig, vermittlung

router = APIRouter()

PRIORITAET_WORT = {"hintergrund": Prioritaet.HINTERGRUND, "normal": Prioritaet.NORMAL, "hoch": Prioritaet.HOCH, "dringend": Prioritaet.DRINGEND}


GETRENNT = "Die Anwendung hat die Verbindung getrennt."


@asynccontextmanager
async def _solange_die_anwendung_wartet(request: Request, v: Vorgang) -> AsyncIterator[None]:
    """Für Antworten ohne Strom: geht die Anwendung, solange ihr Auftrag wartet oder rechnet, endet er wie beim Stoppen.
    Der Abbruch reicht dann bis zum Dienst (die Leitstelle schließt ihre Verbindung, der Dienst hört auf). Ein Strom
    braucht das nicht: dort sieht Starlette das Schließen selbst. Den Körper hat die Fassade schon gelesen; danach kommt auf
    der Verbindung nur noch die Nachricht, dass sie zu ist."""
    async def wache() -> None:
        while (await request.receive())["type"] != "http.disconnect":
            await asyncio.sleep(0.1)
        v.lauf.beenden_mit("anwendung", GETRENNT)

    aufgabe = asyncio.create_task(wache())
    try:
        yield
    finally:
        aufgabe.cancel()


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


def _einordnung(request: Request) -> dict:
    """X-Leitstelle-Art (`einzel` oder `masse`, LS-24), X-Leitstelle-Wichtig (`ja`, LS-23: nur, wenn der Nutzer den
    Auftrag in der App ausdrücklich als wichtig markiert hat) und X-Leitstelle-Rechner (LS-28). Unbekannte Werte zählen
    wie keine Angabe."""
    art = request.headers.get("x-leitstelle-art", "").strip().lower()
    wichtig = request.headers.get("x-leitstelle-wichtig", "").strip().lower() in ("ja", "1", "true")
    return {"art": Auftragsart.MASSE if art == Auftragsart.MASSE.value else Auftragsart.EINZEL, "wichtig": wichtig,
            "rechner": _rechner(request)}


RECHNER_HOECHSTENS = 8


def _rechner(request: Request) -> list[str]:
    """X-Leitstelle-Rechner: Rechner, die die App bevorzugt, durch Komma getrennt in ihrer Reihenfolge (Kennung oder Name,
    prozentkodiert wie der Titel, LS-28). Ein Wunsch: die Leitstelle nimmt den ersten, der gerade kann, sonst weicht sie
    aus. Unbekannte Rechner zählen nicht; leer oder ohne Kopf entscheidet die Leitstelle allein."""
    roh = unquote(request.headers.get("x-leitstelle-rechner", ""))
    knoten = betrieb(request).verbund.knoten
    nach_name = {k.name.casefold(): k.kennung for k in knoten.values()} | {k.casefold(): k for k in knoten}
    wunsch: list[str] = []
    for teil in roh.split(",")[:RECHNER_HOECHSTENS]:
        if (k := nach_name.get(teil.strip().casefold())) and k not in wunsch:
            wunsch.append(k)
    return wunsch


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
    try:
        wahl = Modellwahl.model_validate(koerper)
    except ValidationError as fehler:
        return _eingabefehler(_eingabe_text(fehler))
    koerper.pop("alternativen", None)              # gehört der Leitstelle, nicht dem Dienst
    if faehigkeit == Faehigkeit.TEXT and _bild_im_chat(koerper):
        faehigkeit = Faehigkeit.BILD_BESCHREIBEN
    strom = bool(koerper.get("stream")) and faehigkeit != Faehigkeit.EINBETTUNG
    titel = _titel(request, faehigkeit)
    verm = vermittlung(request)
    try:
        v = verm.annehmen(app.kennung, faehigkeit, wahl.model, _prioritaet(request, app), titel, _arbeit(request), _extern(request), koerper=koerper,
                          alternativen=wahl.alternativen, **_einordnung(request))
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
        async with _solange_die_anwendung_wartet(request, v):
            async for teil in verm.ausfuehren(v, pfad, koerper, False):
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
    a = e.auftrag
    antwort = BildAntwort(created=int(betrieb(request).uhr.jetzt()), data=[BildDaten(b64_json=base64.b64encode(b).decode("ascii")) for b in e.ergebnis.bilder],
                          x_leitstelle=BildZusatz(seed=e.ergebnis.seed, modell=e.familie, groesse=f"{a.breite}x{a.hoehe}", schritte=e.ergebnis.schritte,
                                                  dauer_ms=round(e.dauer_s * 1000)))
    return json.dumps(antwort.model_dump(mode="json", by_alias=True), ensure_ascii=False).encode()


async def bilder(request: Request) -> Response:
    """Bilder erzeugen im OpenAI-Format (PROTOKOLL 6): ein Auftrag mit der Fähigkeit bild_erzeugen. Den Ablauf des
    Bilddienstes kennt nur sein Bildablauf; die Anwendung nennt Beschreibung, Größe, Anzahl und wahlweise Startwert,
    Schritte und Modell. Was das Modell annimmt, prüft die Leitstelle mit seinem Steckbrief, bevor sie einen Dienst startet."""
    app = _anwendung(request)
    if app is None:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt (Kopf Authorization: Bearer ...).")
    try:
        anfrage = BildAnfrage.model_validate(await request.json())
    except ValueError as fehler:
        return _eingabefehler(_eingabe_text(fehler) if isinstance(fehler, ValidationError) else "Der Körper ist kein JSON.")
    return await _bildauftrag(request, app, anfrage, Faehigkeit.BILD_ERZEUGEN)


async def bearbeiten(request: Request) -> Response:
    """Bilder bearbeiten (PROTOKOLL 6.5): ein Auftrag mit der Fähigkeit bild_bearbeiten, mindestens eine Bildvorlage. Als
    Formular wie im OpenAI-Format (Datei im Feld `image`, auch mehrfach oder als `image[]`, die übrigen Felder wie beim
    Erzeugen) oder als JSON mit `images` in Base64. Gerechnet wird wie beim Erzeugen mit Vorlagen; die Bilder gehen nicht
    in die Bildablage, denn es sind Zwischenstände der Anwendung, die das fertige Bild selbst weitergibt."""
    app = _anwendung(request)
    if app is None:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt (Kopf Authorization: Bearer ...).")
    try:
        anfrage = BildAnfrage.model_validate(await _bearbeitung_lesen(request))
    except ValueError as fehler:
        return _eingabefehler(_eingabe_text(fehler) if isinstance(fehler, ValidationError) else str(fehler))
    if not anfrage.images:
        return _eingabefehler("Bild bearbeiten braucht mindestens eine Bildvorlage (Feld image).")
    return await _bildauftrag(request, app, anfrage, Faehigkeit.BILD_BEARBEITEN)


FORMULAR_LISTEN = {"alternativen"}                     # Formularfelder, die mehrfach vorkommen dürfen


async def _bearbeitung_lesen(request: Request) -> dict[str, Any]:
    """Der Körper einer Bearbeitung als Felder der Bildanfrage: JSON unverändert, ein Formular mit den Dateien als Base64."""
    if not request.headers.get("content-type", "").startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        try:
            return await request.json()
        except ValueError:
            raise ValueError("Der Körper ist weder JSON noch ein Formular.") from None
    formular = await request.form()
    felder: dict[str, Any] = {}
    for name in formular.keys():
        if name in ("image", "image[]"):
            continue
        werte = [w for w in formular.getlist(name) if isinstance(w, str)]
        if werte:
            felder[name] = werte if name in FORMULAR_LISTEN else werte[0]
    if "stream" in felder:
        felder["stream"] = felder["stream"].strip().lower() in ("true", "1", "ja")
    dateien = [d for name in ("image", "image[]") for d in formular.getlist(name) if not isinstance(d, str)]
    felder["images"] = [base64.b64encode(await d.read()).decode("ascii") for d in dateien]
    return felder


async def _bildauftrag(request: Request, app: AnwendungEintrag, anfrage: BildAnfrage, faehigkeit: Faehigkeit) -> Response:
    """Ein Bildauftrag nach Fähigkeit (erzeugen oder bearbeiten): Wahl der Anwendung vorab prüfen, einreihen, warten,
    rechnen; mit oder ohne Strom. In die Bildablage gehen nur erzeugte Bilder."""
    verm = vermittlung(request)
    ablegen = faehigkeit == Faehigkeit.BILD_ERZEUGEN
    try:
        # die Wahl der Anwendung, vorab geprüft: kein Dienst startet für eine Anfrage, die keines ihrer Modelle annimmt
        familie, alternativen = verm.bildwahl(app.kennung, anfrage, faehigkeit)
        v = verm.annehmen(app.kennung, faehigkeit, familie, _prioritaet(request, app), _titel(request, faehigkeit),
                          _arbeit(request), _extern(request), alternativen=alternativen, **_einordnung(request))
    except Ablehnung as a:
        return ablehnung_antwort(request, a)
    seed = verm.startwert(anfrage.seed)
    if anfrage.stream:
        return StreamingResponse(_bilder_strom(request, v, anfrage, seed, ablegen), media_type="text/event-stream",
                                 headers={**_kopf(request, v), "Cache-Control": "no-cache"})
    try:
        async with _solange_die_anwendung_wartet(request, v):
            async for _ in verm.warten(v):
                pass
            erzeugung = await verm.bilder_erzeugen(v, anfrage, seed)
        if ablegen:
            await _ablegen(request, v, erzeugung)
    except Ablehnung as a:
        antwort = ablehnung_antwort(request, a)
        antwort.headers.update(_kopf(request, v))
        return antwort
    finally:
        verm.aufraeumen(v)
    kopf = _kopf(request, v) | {"X-Leitstelle-Modell": v.modellname} | ({"X-Leitstelle-Knoten": v.knoten} if v.knoten else {})
    return Response(_bildantwort(request, erzeugung), media_type="application/json", headers=kopf)


async def _ablegen(request: Request, v: Vorgang, e: Bilderzeugung) -> None:
    """Für ein Bildarchiv ablegen (PROTOKOLL 6.3); die Bildablage entscheidet, ob es eines gibt."""
    b = betrieb(request)
    if (app := b.anwendungen.get(v.auftrag.anwendung)) is not None:
        await b.bildablage.ablegen(app, b.anwendungen.values(), v.auftrag.kennung, e.auftrag, e.ergebnis, e.familie, b.uhr.jetzt())


def _archiv(request: Request) -> AnwendungEintrag | JSONResponse:
    app = _anwendung(request)
    if app is None:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt (Kopf Authorization: Bearer ...).")
    if not ist_archiv(app):
        return fehler_antwort(request, "faehigkeit_nicht_erlaubt", "Bilder abholen darf nur ein Bildarchiv (Recht bildarchiv der Anwendung).")
    return app


async def bildablage_liste(request: Request, anzahl: int = 20) -> Response:
    """Die ältesten wartenden Bilder mit ihren Angaben, dazu wie viele insgesamt warten (PROTOKOLL 6.3)."""
    if isinstance(app := _archiv(request), JSONResponse):
        return app
    bilder, wartend, belegt = await betrieb(request).bildablage.wartend(max(1, min(anzahl, 200)))
    return JSONResponse({"bilder": [e.model_dump(mode="json") for e in bilder], "wartend": wartend, "bytes": belegt})


async def bildablage_bild(request: Request, kennung: str) -> Response:
    if isinstance(app := _archiv(request), JSONResponse):
        return app
    gefunden = await betrieb(request).bildablage.datei(kennung)
    if gefunden is None:
        return fehler_antwort(request, "unbekannt", f"Kein wartendes Bild {kennung}.")
    return Response(gefunden[1], media_type="image/png")


async def bildablage_quittieren(request: Request, kennung: str) -> Response:
    """Abgeholt: das Bild fällt aus der Ablage."""
    if isinstance(app := _archiv(request), JSONResponse):
        return app
    if not await betrieb(request).bildablage.quittieren(kennung):
        return fehler_antwort(request, "unbekannt", f"Kein wartendes Bild {kennung}.")
    return Response(status_code=204)


async def _bilder_strom(request: Request, v: Vorgang, anfrage: BildAnfrage, seed: int, ablegen: bool):
    """Wie der Chat: Kommentare, solange der Auftrag wartet, und während der Dienst rechnet, damit die Verbindung offen
    bleibt; dann genau ein `data:` mit der Antwort (oder dem Fehler) und `data: [DONE]`. Geht die Anwendung, endet der
    Auftrag, und der Bilddienst nimmt ihn aus seiner Warteschlange."""
    verm = vermittlung(request)
    arbeit: asyncio.Future[Bilderzeugung] | None = None
    try:
        async for w in verm.warten(v):
            yield _hinweis(w)
        arbeit = asyncio.ensure_future(verm.bilder_erzeugen(v, anfrage, seed))
        seit = 0.0
        while not (await asyncio.wait({arbeit}, timeout=konfig(request).hinweis_s))[0]:
            seit += konfig(request).hinweis_s
            yield f": rechnet seit {seit:.0f} s\n\n".encode()
        if ablegen:
            await _ablegen(request, v, arbeit.result())
        yield b"data: " + _bildantwort(request, arbeit.result()) + b"\n\ndata: [DONE]\n\n"
    except Ablehnung as a:
        daten = json.dumps({"error": fehler_inhalt(a.grund, a.begruendung, a.zusatz)}, ensure_ascii=False)
        yield f"data: {daten}\n\ndata: [DONE]\n\n".encode()
    finally:
        # ohne `await`: reißt die Anwendung ab, wird dieser Rest abgebrochen; der Auftrag braucht seinen Endzustand trotzdem
        if arbeit is not None and not arbeit.done():
            v.lauf.beenden_mit("anwendung", GETRENNT)
        verm.aufraeumen(v)


# Köpfe, die nur einer Verbindung gelten oder die Leitstelle selbst auswertet
OHNE_KOPF = {"host", "authorization", "content-length", "connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
             "x-leitstelle-titel", "x-leitstelle-prioritaet", "x-leitstelle-arbeit", "x-leitstelle-extern", "x-leitstelle-instanz",
             "x-leitstelle-art", "x-leitstelle-wichtig"}


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
                          instanz=_instanz(request, familie), **_einordnung(request))
    except Ablehnung as a:
        return ablehnung_antwort(request, a)
    anfrage = Durchleitung(methode=request.method, pfad=pfad, abfrage=request.url.query, inhalt=await request.body(),
                           kopf={k: w for k, w in request.headers.items() if k.lower() not in OHNE_KOPF})
    try:
        async with _solange_die_anwendung_wartet(request, v):
            async for _ in verm.warten(v):
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


router.add_api_route("/v1/bildablage", bildablage_liste, methods=["GET"], name="bildablage_liste")
router.add_api_route("/v1/bildablage/{kennung}", bildablage_bild, methods=["GET"], name="bildablage_bild")
router.add_api_route("/v1/bildablage/{kennung}", bildablage_quittieren, methods=["DELETE"], name="bildablage_quittieren")
router.add_api_route("/v1/dienste/{name}/{pfad:path}", dienst, methods=["GET", "POST", "PUT", "PATCH", "DELETE"], name="dienst")

for basis in ("/v1", ""):     # Basisadresse mit oder ohne /v1
    router.add_api_route(f"{basis}/chat/completions", chat, methods=["POST"], include_in_schema=basis == "/v1", name=f"chat{basis or '_ohne_v1'}")
    router.add_api_route(f"{basis}/embeddings", einbettung, methods=["POST"], include_in_schema=basis == "/v1", name=f"einbettung{basis or '_ohne_v1'}")
    router.add_api_route(f"{basis}/images/generations", bilder, methods=["POST"], include_in_schema=basis == "/v1", name=f"bilder{basis or '_ohne_v1'}")
    router.add_api_route(f"{basis}/images/edits", bearbeiten, methods=["POST"], include_in_schema=basis == "/v1", name=f"bearbeiten{basis or '_ohne_v1'}")


def _erlaubte_modelle(request: Request, app: AnwendungEintrag | None) -> list[Modell]:
    """Alle Modellinstanzen, die die Anwendung nutzen darf (Fähigkeit und Zone); ohne Schlüssel aus dem Heimnetz alle.
    Gesperrte (im Maschinenraum nach einem Speicherabbruch oder von Hand) bietet die Leitstelle nicht an: sie nehmen bis
    zum Aufheben der Sperre keinen Auftrag an (HELF-84)."""
    b = betrieb(request)
    aus = []
    for m in b.verbund.modelle.values():
        d = b.verbund.dienste.get(m.dienst)
        if d is None or m.sperre:
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
                      "x-leitstelle": {"name": m.name, "aufgabe": m.aufgabe, "geladen": m.zustand != Modellzustand.FREI, "knoten": d.knoten, "extern": d.extern,
                                       "knoten_name": b.verbund.knoten[d.knoten].name if d.knoten in b.verbund.knoten else None,
                                       "faehigkeiten": sorted(f.value for f in m.faehigkeiten), "gb": m.gb,
                                       "steckbrief": b.steckbrief(m).model_dump(mode="json")}})
    return {"object": "list", "data": daten}


@router.get("/v1/lage")
async def lage(request: Request):
    """Auskunft für Apps (PROTOKOLL 6.5): Auslastung je App, Modelle je Rechner, geschätzte Dauer, Rangfolge und Priorität,
    ohne Inhalte. Mit App-Schlüssel sind die eigenen Aufträge markiert."""
    darf, app = _darf_lesen(request)
    if not darf:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt.")
    return lageauskunft(betrieb(request), app.kennung if app else None).model_dump(mode="json")


@router.post("/v1/einschaetzung")
async def einschaetzung_route(request: Request):
    """Einschätzung vor dem Senden (LS-23, PROTOKOLL 6.6): was mit diesem Auftrag jetzt geschähe; nichts wird eingereiht."""
    app = _anwendung(request)
    if app is None:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt (Kopf Authorization: Bearer ...).")
    try:
        anfrage = Einschaetzungsanfrage.model_validate(await request.json())
    except (ValidationError, ValueError) as fehler:
        return _eingabefehler(_eingabe_text(fehler) if isinstance(fehler, ValidationError) else "Inhalt ist kein JSON.")
    verm = vermittlung(request)
    try:
        familie, alternativen = verm.modellwahl(anfrage.model, anfrage.alternativen)
        faehigkeit = anfrage.faehigkeit or (verm.faehigkeit_fuer(app.kennung, familie) if familie else Faehigkeit.TEXT)
    except Ablehnung as a:
        return ablehnung_antwort(request, a)
    return einschaetzung(betrieb(request), app.kennung, anfrage, faehigkeit, familie, alternativen).model_dump(mode="json")


@router.post("/v1/einordnen")
async def einordnen_route(request: Request):
    """Einordnen (LS-26, PROTOKOLL 6.7): Text und Fragen mit festen Möglichkeiten; Antwort je Frage die Wahl und die
    Wahrscheinlichkeiten. Jeder Aufruf des Modells ist ein Auftrag der Fähigkeit `einordnen` mit den Köpfen der Anfrage
    (Titel, Priorität, Art, Wichtig); ohne eigene Arbeit gehören alle zu einer Arbeit dieser Anfrage."""
    app = _anwendung(request)
    if app is None:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt (Kopf Authorization: Bearer ...).")
    try:
        anfrage = Einordnungsanfrage.model_validate(await request.json())
    except (ValidationError, ValueError) as fehler:
        return _eingabefehler(_eingabe_text(fehler) if isinstance(fehler, ValidationError) else "Inhalt ist kein JSON.")
    b, verm = betrieb(request), vermittlung(request)
    titel, prioritaet, extern = _titel(request, Faehigkeit.EINORDNEN), _prioritaet(request, app), _extern(request)
    arbeit, einordnung = _arbeit(request) or f"einordnen-{uuid4().hex[:12]}", _einordnung(request)
    zuletzt: list[Vorgang] = []

    async def rechnen(koerper: dict[str, Any]) -> bytes:
        v = verm.annehmen(app.kennung, Faehigkeit.EINORDNEN, anfrage.model, prioritaet, titel, arbeit, extern, koerper=koerper,
                          alternativen=anfrage.alternativen, **einordnung)
        zuletzt[:] = [v]
        teile: list[bytes] = []
        try:
            async with _solange_die_anwendung_wartet(request, v):
                async for teil in verm.ausfuehren(v, "/v1/chat/completions", koerper, False):
                    if not isinstance(teil, Wartet):
                        teile.append(teil)
        finally:
            verm.aufraeumen(v)
        if v.auftrag.zustand != Auftragszustand.FERTIG:
            raise Ablehnung(v.auftrag.grund or "dienst_fehler", v.auftrag.begruendung or "abgebrochen", v.lauf.zusatz)
        return b"".join(teile)

    start = b.uhr.jetzt()
    try:
        antworten, anzahl = await einordnen(anfrage, rechnen)
    except Ablehnung as a:
        antwort = ablehnung_antwort(request, a)
        if zuletzt:
            antwort.headers.update(_kopf(request, zuletzt[0]))
        return antwort
    v = zuletzt[0]
    kopf = _kopf(request, v) | {"X-Leitstelle-Modell": v.modellname} | ({"X-Leitstelle-Knoten": v.knoten} if v.knoten else {})
    ergebnis = Einordnung(antworten=antworten, modell=v.modellname, anfragen=anzahl, dauer_ms=round((b.uhr.jetzt() - start) * 1000))
    return JSONResponse(ergebnis.model_dump(mode="json"), headers=kopf)


#: Strom der Auskunft: so oft wird auf Änderungen geschaut, so lange darf er ohne Änderung still sein (Kommentar hält ihn offen)
STROM_TAKT_S = 1.0
STROM_STILL_S = 15.0


@router.get("/v1/lage/strom")
async def lage_strom(request: Request):
    """Dieselbe Auskunft als Strom (Server-Sent Events): `event: lage` bei jeder Änderung, sonst alle 15 s ein Kommentar."""
    darf, app = _darf_lesen(request)
    if not darf:
        return fehler_antwort(request, "unbekannter_schluessel", "Schlüssel fehlt oder ist unbekannt.")
    b = betrieb(request)
    fragt = app.kennung if app else None

    async def sse() -> AsyncIterator[bytes]:
        gesendet, still = -1, 0.0
        while not await request.is_disconnected():
            if b.aenderung != gesendet:
                gesendet, still = b.aenderung, 0.0
                yield f"event: lage\ndata: {lageauskunft(b, fragt).model_dump_json()}\n\n".encode()
            elif still >= STROM_STILL_S:
                still = 0.0
                yield b": ruhig\n\n"
            await asyncio.sleep(STROM_TAKT_S)
            still += STROM_TAKT_S

    return StreamingResponse(sse(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


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
                    {"id": m.familie, "name": m.name, "aufgabe": m.aufgabe, "geladen": m.zustand != Modellzustand.FREI, "steckbrief": s.model_dump(mode="json")}))
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
    """Die Dienste im Maschinenraum, die die Anwendung nutzen darf (PROTOKOLL 6.2): Kennung, Name, Aufgabe, Zweck, Fähigkeiten,
    Zustand, Rechner und bei Bilddiensten ihr Bild-Steckbrief; je Dienst ein Eintrag, gleich wie viele Instanzen auf wie
    vielen Rechnern laufen."""
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
        steckbrief = b.steckbrief(grund)
        aus.append(DienstSicht(kennung=familie, name=grund.name, aufgabe=grund.aufgabe, zweck=steckbrief.zweck, faehigkeiten=[f for f in Faehigkeit if f in faehig],
                               zustand=min((_bereitschaft(request, m) for m in instanzen), key=BEREITSCHAFT_VORRANG.index),
                               rechner=sorted(b.verbund.knoten[k].name for k in knoten if k in b.verbund.knoten),
                               orte=sorted((RechnerOrt(kennung=k, name=b.verbund.knoten[k].name) for k in knoten if k in b.verbund.knoten),
                                           key=lambda o: o.name),
                               bild=steckbrief.bild))
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
