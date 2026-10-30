"""Externer Anbieter wie Hetzner (ZUSAMMENSPIEL Z4): seltener Abgleich, jede Anfrage zählt, wachsende Prüfabstände bis
zum Ausfall, "jetzt prüfen", Sperre und Neueinreihen nach 429 und nach 504 des Vorschaltrechners (Anbieter ausgelastet).
Die Uhr steht, bis der Test sie stellt."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from leitstelle.api.app import erstellen
from leitstelle.api.fassade import _extern
from leitstelle.fach.vermittlung import UEBERLAST_WARTE_S
from leitstelle.konfig import Konfig
from leitstelle.ports.uhr import Stelluhr

from schein.server import laufend
from test_adapter import HETZNER_MODELLE


def schein_hetzner() -> FastAPI:
    app = FastAPI()
    app.state.an, app.state.zu_viel, app.state.ausgelastet, app.state.pfade = True, 0, 0, []

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
        if _mit_bild(app.state.koerper):                # Fähigkeitsprobe: das dichte Modell nimmt keine Bilder an, das Mischmodell sieht Rot
            if app.state.koerper["model"] in ("Qwen/Qwen3.8-27B", "Qwen3.8-27B"):
                return JSONResponse({"error": {"message": "image input is not supported for this model"}}, status_code=400)
            stuecke = [{"choices": [{"index": 0, "delta": {"reasoning_content": "Das Bild ist einfarbig. "}}]},
                       {"choices": [{"index": 0, "delta": {"content": "Rot."}, "finish_reason": "stop"}]},
                       {"choices": [], "usage": {"prompt_tokens": 290, "completion_tokens": 12}}]
            sse = "".join(f"data: {json.dumps({'id': 'b', 'model': app.state.koerper['model'], **t})}\n\n" for t in stuecke) + "data: [DONE]\n\n"
            return StreamingResponse(iter([sse.encode()]), media_type="text/event-stream")
        if app.state.zu_viel:
            app.state.zu_viel -= 1
            return JSONResponse({"error": {"message": "rate limit"}}, status_code=429, headers={"Retry-After": "7"})
        if app.state.ausgelastet:                       # wie Hetzner, wenn das Modell 300 s lang nicht anfängt
            app.state.ausgelastet -= 1
            return HTMLResponse("<title>504 - Gateway Timeout</title>", status_code=504)
        if not app.state.koerper.get("stream"):        # wie Hetzner bei langem Denken: still, dann 504 nach der Frist
            return JSONResponse({"error": "Gateway Timeout"}, status_code=504)
        stuecke = [{"choices": [{"index": 0, "delta": {"reasoning_content": "erst denken "}}]},
                   {"choices": [{"index": 0, "delta": {"content": "hal"}}]},
                   {"choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": "stop"}]},
                   {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 7}}]
        sse = "".join(f"data: {json.dumps({'id': 'x', 'model': 'Qwen/Qwen3.8-27B', **t})}\n\n" for t in stuecke) + "data: [DONE]\n\n"
        return StreamingResponse(iter([sse.encode()]), media_type="text/event-stream")

    return app


def _mit_bild(koerper: dict) -> bool:
    return any(isinstance(n.get("content"), list) and any(t.get("type") == "image_url" for t in n["content"]) for n in koerper.get("messages") or [])


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
            assert sicht["zustand"] == "bereit" and sicht["nutzung"]["anfragen"] == 1 and sicht["anfragen_je_minute"] == 10
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

            # 504 des Vorschaltrechners (Anbieter ausgelastet): wie Überlast gesperrt, kein Fehlschlag, Auftrag kommt durch
            hetzner.state.ausgelastet = 1
            d = b.verbund.dienste[dienst]
            async with httpx.AsyncClient(base_url=url + "/v1", timeout=30, headers={"Authorization": f"Bearer {schluessel}"}) as anw:
                anfrage = asyncio.create_task(anw.post("/chat/completions", json={"model": "Qwen3.8-27B", "messages": []}))
                for _ in range(200):
                    if (d.gesperrt_bis_s or 0) > uhr.zeit:
                        break
                    await asyncio.sleep(0.02)
                assert d.gesperrt_bis_s == uhr.zeit + UEBERLAST_WARTE_S, "ohne Retry-After die feste Sperre"
                assert d.zustand.value == "bereit" and b.pruefstand[dienst].fehlschlaege == 0, "Überlast ist kein Fehlschlag"
                b.anstossen()
                await asyncio.sleep(0.2)
                assert not anfrage.done(), "wartet, solange der Anbieter gesperrt ist"
                wartend = [a for a in b.verbund.auftraege.values() if a.zustand.value == "eingereiht"]
                assert len(wartend) == 1 and "Dienst meldete Überlast" in wartend[0].begruendung, wartend
                uhr.zeit += UEBERLAST_WARTE_S + 1
                b.anstossen()
                antwort = await asyncio.wait_for(anfrage, 10)
            assert antwort.status_code == 200 and antwort.json()["choices"][0]["message"]["content"] == "hallo"
            assert hetzner.state.pfade.count("/api/v1/chat/completions") == 4


@asynccontextmanager
async def hetzner_aufbau(tmp_path, uhr: Stelluhr, **grenzen):
    """Leitstelle mit dem Schein-Anbieter wie Hetzner (zwei Modelle), Grenzen nach Wunsch, und einer Anwendung, die extern darf."""
    hetzner = schein_hetzner()
    async with laufend(hetzner) as ziel:
        app = erstellen(Konfig(daten=tmp_path, oberflaeche=None), uhr=uhr, transport=Umleitung(ziel), mit_takt=False)
        async with laufend(app) as url, httpx.AsyncClient(base_url=url, timeout=30) as c:
            r = await c.post("/api/dienste", json={"adresse": "https://hetzner.test/api/v1", "extern": True, "zugang": "geheim", "name": "Hetzner",
                                                   "anfragen_je_minute": 10, **grenzen})
            assert r.status_code == 200, r.text
            r2 = await c.post("/api/anwendungen", json={"name": "Probe", "zonen": ["heim", "extern"], "extern_erlaubt": True,
                                                        "faehigkeiten": ["text", "bild_beschreiben"]})
            async with httpx.AsyncClient(base_url=url + "/v1", timeout=30, headers={"Authorization": f"Bearer {r2.json()['schluessel']}"}) as anw:
                yield SimpleNamespace(c=c, anw=anw, app=app, b=app.state.betrieb, dienst=r.json()["kennung"], hetzner=hetzner, url=url)


async def _modelle(c, dienst: str) -> dict[str, dict]:
    return {m["name"]: m for m in (await c.get("/api/lage")).json()["modelle"] if m["dienst"] == dienst}


async def _dienst(c, dienst: str) -> dict:
    return next(d for d in (await c.get("/api/lage")).json()["dienste"] if d["kennung"] == dienst)


async def test_x01_zwei_modelle_einzeln_mit_steckbrief(tmp_path):
    """Beide Modelle mit Kontext aus max_model_len, Parametern gesamt und aktiv (A3B: 3) und ihrer Rolle im Vergleich:
    das Mischmodell schnell, das dichte gründlich, abgeleitet; für die Apps in /v1/models und /v1/steckbriefe."""
    async with hetzner_aufbau(tmp_path, Stelluhr(), token_ein_je_minute=4_000_000, token_aus_je_minute=100_000) as h:
        ms = await _modelle(h.c, h.dienst)
        schnell, gruendlich = ms["Qwen3.6-35B-A3B"]["steckbrief"], ms["Qwen3.8-27B"]["steckbrief"]
        assert (schnell["kontext"], schnell["parameter_mrd"], schnell["parameter_aktiv_mrd"]) == (262144, 35, 3)
        assert (gruendlich["parameter_mrd"], gruendlich["parameter_aktiv_mrd"]) == (27, 27)
        assert schnell["eignung"] == ["lange_texte", "schnell"] and gruendlich["eignung"] == ["lange_texte", "gruendlich"]
        assert schnell["zweck"].startswith("Schnell") and schnell["herkunft"]["zweck"] == "abgeleitet" and schnell["herkunft"]["parameter_aktiv_mrd"] == "abgeleitet"
        assert schnell["token_aus_je_minute"] == 100_000 and schnell["zone"] == "extern"
        assert all(m["zustand"] == "geladen" and m["gb"] == 0 for m in ms.values()), "beim Anbieter immer bereit, ohne Speicher"
        daten = {m["id"]: m["x-leitstelle"] for m in (await h.anw.get("/models")).json()["data"]}
        assert {"Qwen/Qwen3.6-35B-A3B", "Qwen/Qwen3.8-27B"} <= set(daten) and daten["Qwen/Qwen3.8-27B"]["steckbrief"]["eignung"][-1] == "gruendlich"
        assert [m["id"] for m in (await h.anw.get("/steckbriefe", params={"eignung": "schnell"})).json()["data"]] == ["Qwen/Qwen3.6-35B-A3B"]
        # von Hand: aktive Parameter für ein Mischmodell, dessen Name es nicht sagt
        r = await h.c.put("/api/steckbriefe", json={"familie": "Qwen/Qwen3.8-27B", "parameter_aktiv_mrd": 4})
        assert r.status_code == 200
        gruendlich = (await _modelle(h.c, h.dienst))["Qwen3.8-27B"]["steckbrief"]
        assert gruendlich["parameter_aktiv_mrd"] == 4 and gruendlich["herkunft"]["parameter_aktiv_mrd"] == "hand" and "gruendlich" not in gruendlich["eignung"]


async def test_x02_nutzung_je_modell_und_token_grenze(tmp_path):
    """Je Modell Anfragen und Token im Fenster neben dem ganzen Schlüssel; die Grenze der Token heraus hält die Leitstelle
    ein (geschätzt aus max_tokens, nach der Antwort echt aus usage)."""
    uhr = Stelluhr()
    async with hetzner_aufbau(tmp_path, uhr, token_aus_je_minute=10) as h:
        r = await h.anw.post("/chat/completions", json={"model": "Qwen3.8-27B", "messages": [{"role": "user", "content": "hallo"}]})
        assert r.status_code == 200 and r.json()["usage"] == {"prompt_tokens": 3, "completion_tokens": 7}
        ms = await _modelle(h.c, h.dienst)
        assert ms["Qwen3.8-27B"]["nutzung"] == {"anfragen": 1, "token_ein": 3, "token_aus": 7, "geschaetzt": False}
        assert ms["Qwen3.6-35B-A3B"]["nutzung"]["anfragen"] == 0 and ms["Qwen3.8-27B"]["belegt"] == 0 and ms["Qwen3.8-27B"]["plaetze"] == 4
        d = await _dienst(h.c, h.dienst)
        assert d["nutzung"]["anfragen"] == 2 and d["nutzung"]["token_aus"] == 7 and d["token_aus_je_minute"] == 10, "mit der Abfrage der Modelle"
        anfrage = asyncio.create_task(h.anw.post("/chat/completions", json={"model": "Qwen3.8-27B", "max_tokens": 5, "messages": []}))
        for _ in range(100):
            wartend = [a for a in h.b.verbund.auftraege.values() if a.zustand.value == "eingereiht"]
            if wartend:
                break
            await asyncio.sleep(0.02)
        assert "Grenze von 10 Token heraus je Minute erreicht" in wartend[0].begruendung
        assert wartend[0].voraussichtlich_s == 60
        assert (await _dienst(h.c, h.dienst))["frei_in_s"] == 0, "eine Anfrage ohne max_tokens passt noch: sie verlangt keine Token heraus"
        uhr.zeit += 61
        h.b.anstossen()
        antwort = await asyncio.wait_for(anfrage, 10)
        assert antwort.status_code == 200 and h.hetzner.state.pfade.count("/api/v1/chat/completions") == 2


async def test_x03_strom_ohne_verbrauchswunsch_der_app(tmp_path):
    """Zum Anbieter fordert die Leitstelle den Verbrauch an (Token heraus aus usage im Strom); eine Anwendung, die ihn nicht
    wollte, bekommt kein Stück ohne choices."""
    async with hetzner_aufbau(tmp_path, Stelluhr()) as h:
        r = await h.anw.post("/chat/completions", json={"model": "Qwen3.8-27B", "stream": True, "messages": [{"role": "user", "content": "hallo"}]})
        assert r.status_code == 200 and h.hetzner.state.koerper["stream_options"] == {"include_usage": True}
        teile = [json.loads(z[6:]) for z in r.text.splitlines() if z.startswith("data: {")]
        assert teile and all(t.get("choices") for t in teile), "kein Stück nur mit usage"
        kennung = r.headers["x-leitstelle-auftrag"]
        for _ in range(100):                           # der Verlauf wird im Hintergrund geschrieben
            e = (await h.c.get(f"/api/auftraege/{kennung}")).json()
            if e.get("zustand") == "fertig":          # vorher 404 ohne Zustand, solange er nicht geschrieben ist
                break
            await asyncio.sleep(0.05)
        assert (e["token_ein"], e["token_aus"]) == (3, 7)
        r = await h.anw.post("/chat/completions", json={"model": "Qwen3.8-27B", "stream": True, "stream_options": {"include_usage": True}, "messages": []})
        assert any('"usage"' in z for z in r.text.splitlines()), "wer es will, bekommt es"


async def test_x04_faehigkeitsprobe_von_hand(tmp_path):
    """Bild beschreiben nur, wenn belegt: je Modell ein kleines Bild mit einer Frage, von Hand ausgelöst; Ergebnis mit
    Zeitpunkt im Steckbrief (Quelle gemessen), in den Fähigkeiten, im Prüfprotokoll; jede Probe zählt; nach dem Neustart da."""
    uhr = Stelluhr()
    async with hetzner_aufbau(tmp_path, uhr) as h:
        vorher = (await _dienst(h.c, h.dienst))["nutzung"]["anfragen"]
        r = await h.c.post(f"/api/dienste/{h.dienst}/faehigkeiten_pruefen")
        assert r.status_code == 200, r.text
        aus = {x["name"]: x for x in r.json()}
        assert aus["Qwen3.6-35B-A3B"]["ausgang"] == "belegt" and "Rot" in aus["Qwen3.6-35B-A3B"]["meldung"]
        assert aus["Qwen3.8-27B"]["ausgang"] == "nicht_belegt" and "image input is not supported" in aus["Qwen3.8-27B"]["meldung"]
        ms = await _modelle(h.c, h.dienst)
        assert "bild_beschreiben" in ms["Qwen3.6-35B-A3B"]["faehigkeiten"] and "bild_beschreiben" not in ms["Qwen3.8-27B"]["faehigkeiten"]
        probe = ms["Qwen3.6-35B-A3B"]["steckbrief"]["geprueft"][0]
        assert probe["faehigkeit"] == "bild_beschreiben" and probe["belegt"] and probe["zeit_s"] == uhr.zeit
        assert ms["Qwen3.6-35B-A3B"]["steckbrief"]["herkunft"]["geprueft"] == "gemessen"
        d = await _dienst(h.c, h.dienst)
        assert d["nutzung"]["anfragen"] == vorher + 2 and d["nutzung"]["token_ein"] >= 290, "jede Probe zählt, mit ihrem Verbrauch"
        pruef = [e["was"] for e in (await h.c.get("/api/pruefprotokoll")).json()["eintraege"]]
        assert "Fähigkeiten geprüft: Qwen3.6-35B-A3B Bild beschreiben belegt und Qwen3.8-27B Bild beschreiben nicht belegt" in pruef
        bild = {"role": "user", "content": [{"type": "text", "text": "Was ist das?"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}]}
        r = await h.anw.post("/chat/completions", json={"model": "Qwen/Qwen3.6-35B-A3B", "messages": [bild]})
        assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "Rot."
        r = await h.anw.post("/chat/completions", json={"model": "Qwen3.8-27B", "messages": [bild]})
        assert r.status_code == 404 and r.json()["error"]["code"] == "kein_modell", "ohne belegte Fähigkeit kein Bild an dieses Modell"
        assert (await h.c.post("/api/dienste/gibt-es-nicht/faehigkeiten_pruefen")).status_code == 404
    async with hetzner_aufbau(tmp_path / "neu", Stelluhr()) as h2:
        assert "bild_beschreiben" not in (await _modelle(h2.c, h2.dienst))["Qwen3.6-35B-A3B"]["faehigkeiten"], "frische Ablage: nichts geprüft"
    hetzner = schein_hetzner()
    async with laufend(hetzner) as ziel:
        app = erstellen(Konfig(daten=tmp_path, oberflaeche=None), uhr=Stelluhr(), transport=Umleitung(ziel), mit_takt=False)
        async with laufend(app) as url, httpx.AsyncClient(base_url=url, timeout=30) as c:
            d = next(x for x in (await c.get("/api/lage")).json()["dienste"] if x["name"] == "Hetzner")
            assert "bild_beschreiben" in (await _modelle(c, d["kennung"]))["Qwen3.6-35B-A3B"]["faehigkeiten"], "nach dem Neustart geladen"


async def test_x05_probe_nur_innerhalb_der_grenze(tmp_path):
    """Die Probe kostet je Modell eine Anfrage; reicht die Grenze dafür nicht, lehnt die Leitstelle mit Wartezeit ab."""
    async with hetzner_aufbau(tmp_path, Stelluhr(), anfragen_je_minute=2) as h:
        r = await h.c.post(f"/api/dienste/{h.dienst}/faehigkeiten_pruefen")
        assert r.status_code == 429 and r.json()["grund"] == "grenze" and "Grenze von 2 Anfragen je Minute erreicht" in r.json()["begruendung"]
        assert h.hetzner.state.pfade.count("/api/v1/chat/completions") == 0
