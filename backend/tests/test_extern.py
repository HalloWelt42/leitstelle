"""Externer Anbieter wie Hetzner (ZUSAMMENSPIEL Z4): seltener Abgleich, jede Anfrage zählt, wachsende Prüfabstände bis
zum Ausfall, "jetzt prüfen", Sperre und Neueinreihen nach 429. Die Uhr steht, bis der Test sie stellt."""

from __future__ import annotations

import asyncio
import json

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from leitstelle.api.app import erstellen
from leitstelle.api.fassade import _extern
from leitstelle.konfig import Konfig
from leitstelle.ports.uhr import Stelluhr

from schein.server import laufend
from test_adapter import HETZNER_MODELLE


def schein_hetzner() -> FastAPI:
    app = FastAPI()
    app.state.an, app.state.zu_viel, app.state.pfade = True, 0, []

    @app.middleware("http")
    async def mitschreiben(anfrage: Request, weiter):
        app.state.pfade.append(anfrage.url.path)
        if not app.state.an:
            return JSONResponse({"error": {"message": "gewartet"}}, status_code=503)
        return await weiter(anfrage)

    @app.get("/api/v1/models")
    async def liste():
        return HETZNER_MODELLE

    @app.post("/api/v1/chat/completions")
    async def antworten(anfrage: Request):
        app.state.koerper = await anfrage.json()
        if app.state.zu_viel:
            app.state.zu_viel -= 1
            return JSONResponse({"error": {"message": "rate limit"}}, status_code=429, headers={"Retry-After": "7"})
        if not app.state.koerper.get("stream"):        # wie Hetzner bei langem Denken: still, dann 504 nach der Frist
            return JSONResponse({"error": "Gateway Timeout"}, status_code=504)
        stuecke = [{"choices": [{"index": 0, "delta": {"reasoning_content": "erst denken "}}]},
                   {"choices": [{"index": 0, "delta": {"content": "hal"}}]},
                   {"choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": "stop"}]},
                   {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 7}}]
        sse = "".join(f"data: {json.dumps({'id': 'x', 'model': 'Qwen/Qwen3.8-27B', **t})}\n\n" for t in stuecke) + "data: [DONE]\n\n"
        return StreamingResponse(iter([sse.encode()]), media_type="text/event-stream")

    return app


class Umleitung(httpx.AsyncBaseTransport):
    """Externe Anbieter nur über https: die Leitstelle spricht https://hetzner.test, der Test leitet auf den Schein um."""

    def __init__(self, ziel: str) -> None:
        self.ziel = httpx.URL(ziel)
        self.weiter = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, anfrage: httpx.Request) -> httpx.Response:
        anfrage.url = anfrage.url.copy_with(scheme=self.ziel.scheme, host=self.ziel.host, port=self.ziel.port)
        return await self.weiter.handle_async_request(anfrage)


def modell_abfragen(hetzner: FastAPI) -> int:
    return hetzner.state.pfade.count("/api/v1/models")


async def test_e19_externer_anbieter_grenze_ausfall_und_ueberlast(tmp_path):
    hetzner, uhr = schein_hetzner(), Stelluhr()
    async with laufend(hetzner) as ziel:
        k = Konfig(daten=tmp_path, oberflaeche=None, ausfall_ab_fehlschlag=3)
        app = erstellen(k, uhr=uhr, transport=Umleitung(ziel), mit_takt=False)
        async with laufend(app) as url, httpx.AsyncClient(base_url=url, timeout=30) as c:
            r = await c.post("/api/dienste", json={"adresse": "https://hetzner.test/api/v1", "extern": True, "zugang": "geheim",
                                                   "name": "Hetzner", "anfragen_je_minute": 10})
            assert r.status_code == 200, r.text
            dienst = r.json()["kennung"]
            b = app.state.betrieb
            sicht = next(d for d in (await c.get("/api/lage")).json()["dienste"] if d["kennung"] == dienst)
            assert sicht["zustand"] == "bereit" and sicht["anfragen_letzte_minute"] == 1 and sicht["anfragen_je_minute"] == 10
            assert sicht["naechste_pruefung_s"] == uhr.zeit + k.extern_abgleich_s, "gesund: selten fragen, jede Abfrage zählt"
            namen = sorted(m["name"] for m in (await c.get("/api/lage")).json()["modelle"] if m["dienst"] == dienst)
            assert namen == ["Qwen3.6-35B-A3B", "Qwen3.8-27B"], "Namen mit gleichem root sind ein Modell"

            # Erlaubnisliste der App (Kopf X-Leitstelle-Extern): Namen und Aliasse zu Familien, Unbekanntes fällt weg
            anfrage = Request({"type": "http", "app": app, "headers": [(b"x-leitstelle-extern", b"Qwen3.8-27B,%20Qwen/Qwen3.6-35B-A3B-FP8,%20gibt-es-nicht")]})
            assert _extern(anfrage) == ["Qwen/Qwen3.6-35B-A3B", "Qwen/Qwen3.8-27B"]
            assert _extern(Request({"type": "http", "app": app, "headers": []})) == [], "ohne Kopf nichts nach extern"

            await b.abgleichen()
            assert modell_abfragen(hetzner) == 1, "vor der Frist keine Abfrage"

            # Ausfall: wachsende Abstände 5, 10, 20 s; ab dem dritten Fehlschlag Ausfall
            hetzner.state.an = False
            uhr.zeit += k.extern_abgleich_s
            zustaende = []
            for abstand in (5, 10, 20):
                await b.abgleichen()
                zustaende.append(b.verbund.dienste[dienst].zustand.value)
                assert b.pruefstand[dienst].naechste_s == uhr.zeit + abstand
                uhr.zeit += abstand - 1
                abfragen = modell_abfragen(hetzner)
                await b.abgleichen()
                assert modell_abfragen(hetzner) == abfragen, "vor dem Abstand keine Abfrage"
                uhr.zeit += 1
            assert zustaende == ["nicht_erreichbar", "nicht_erreichbar", "ausfall"]

            # Jetzt prüfen: sofort, und mit Antwort wieder der normale Abstand
            hetzner.state.an = True
            r = await c.post(f"/api/dienste/{dienst}/pruefen")
            assert r.json()["zustand"] == "bereit" and b.pruefstand[dienst].fehlschlaege == 0

            # 429: Dienst gesperrt für Retry-After, Auftrag neu eingereiht, nach der Sperre beantwortet
            r = await c.post("/api/anwendungen", json={"name": "Probe", "zonen": ["heim", "extern"], "extern_erlaubt": True})
            schluessel = r.json()["schluessel"]
            hetzner.state.zu_viel = 1
            async with httpx.AsyncClient(base_url=url + "/v1", timeout=30, headers={"Authorization": f"Bearer {schluessel}"}) as anw:
                anfrage = asyncio.create_task(anw.post("/chat/completions", json={"model": "Qwen3.8-27B", "messages": []}))
                for _ in range(200):
                    if b.verbund.dienste[dienst].gesperrt_bis_s:
                        break
                    await asyncio.sleep(0.02)
                assert b.verbund.dienste[dienst].gesperrt_bis_s == uhr.zeit + 7
                await asyncio.sleep(0.2)
                assert not anfrage.done(), "wartet, solange der Dienst gesperrt ist"
                uhr.zeit += 8
                b.anstossen()
                antwort = await asyncio.wait_for(anfrage, 10)
            assert antwort.status_code == 200 and antwort.json()["choices"][0]["message"]["content"] == "hallo"
            assert hetzner.state.koerper["stream"] is True, "zum Anbieter immer als Strom (Vorschaltrechner brechen stille Anfragen ab)"
            assert antwort.json()["choices"][0]["message"]["reasoning_content"] == "erst denken "
            assert antwort.json()["usage"]["completion_tokens"] == 7, "Verbrauch aus dem Strom"
            assert hetzner.state.pfade.count("/api/v1/chat/completions") == 2
