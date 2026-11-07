"""Auskunft für Apps (LS-18, PROTOKOLL 6.5): `GET /v1/lage` und `GET /v1/lage/strom`. Szenarien S77 bis S79."""

from __future__ import annotations

import asyncio
import json

import httpx

from test_schlaf import MODELL, _warte_bis, aufbau

TITEL = "Geheimer Titel einer Arbeit"


async def test_s77_auskunft_ohne_inhalte_mit_eigenen_auftraegen(tmp_path):
    """Ein laufender Auftrag der App erscheint mit Fähigkeit, Rang, Modell, Rechner und geschätzter Dauer, als eigener
    markiert; Titel und Texte stehen nirgends darin."""
    async with aufbau(tmp_path) as a:
        a.laeufer.stueck_pause_s, a.laeufer.stuecke = 0.2, 30          # die Antwort dauert einige Sekunden
        anfrage = asyncio.create_task(a.anw.post("/v1/chat/completions", json={"model": MODELL, "stream": True,
                                                                                 "messages": [{"role": "user", "content": "Bitte geheim"}]},
                                                 headers={"X-Leitstelle-Titel": TITEL.replace(" ", "%20")}))

        async def laeuft():
            r = await a.anw.get("/v1/lage")
            return any(x["laufend"] for x in r.json()["apps"])
        await _warte_bis(laeuft)
        r = await a.anw.get("/v1/lage")
        assert r.status_code == 200
        text = r.text
        assert "Geheimer" not in text and "Bitte geheim" not in text, "keine Titel, keine Texte"
        lage = r.json()
        app = next(x for x in lage["apps"] if x["name"] == "Transkription")
        auftrag = app["auftraege"][0]
        assert app["eigene"] and auftrag["eigener"] and auftrag["faehigkeit"] == "text" and auftrag["rang"] == 3
        assert auftrag["modell"] == MODELL and auftrag["rechner"] == "Mac Studio" and auftrag["zustand"] in ("laeuft", "zugeteilt")
        mac = next(x for x in lage["rechner"] if x["name"] == "Mac Studio")
        assert any(m["familie"] == MODELL for m in mac["modelle"]) and mac["akku_gesperrt"] is False
        assert lage["rangfolge"]["stimme"] == 1 and lage["rangfolge"]["einbettung"] == 7
        await anfrage


async def test_s78_fremder_schluessel_abgewiesen(tmp_path):
    async with aufbau(tmp_path) as a:
        async with httpx.AsyncClient(base_url=a.url, headers={"Authorization": "Bearer falsch"}) as c:
            assert (await c.get("/v1/lage")).status_code == 401
            assert (await c.get("/v1/lage/strom")).status_code == 401


async def test_s79_strom_liefert_die_lage(tmp_path):
    async with aufbau(tmp_path) as a:
        async with a.anw.stream("GET", "/v1/lage/strom") as antwort:
            assert antwort.status_code == 200 and antwort.headers["content-type"].startswith("text/event-stream")
            zeilen = antwort.aiter_lines()
            assert await asyncio.wait_for(zeilen.__anext__(), 5) == "event: lage"
            daten = await asyncio.wait_for(zeilen.__anext__(), 5)
            lage = json.loads(daten.removeprefix("data: "))
            assert {"apps", "rechner", "rangfolge", "hauptregler"} <= set(lage)
