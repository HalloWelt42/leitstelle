"""Adapter openai_kompatibel gegen den Schein-Läufer: Zustand lesen, laden, entladen, durchleiten,
Rückfall auf die reine OpenAI-Liste, nicht erreichbar."""

import json

from fastapi import FastAPI

from leitstelle.kern.werte import Faehigkeit as F
from leitstelle.ports.dienste import DienstFehler
from leitstelle.ports.dienste.openai_kompatibel import OpenAIKompatibel, _milliarden

from schein.laeufer import schein_laeufer
from schein.server import laufend


def test_parameterzahl_lesen():
    assert _milliarden("80B") == 80 and _milliarden("567M") == 0.567 and _milliarden(None) is None and _milliarden("viel") is None


async def test_zustand_laden_entladen_strom():
    app = schein_laeufer()
    async with laufend(app) as adresse:
        a = OpenAIKompatibel(adresse + "/v1")      # Basisadresse mit /v1 wird angenommen
        b = await a.zustand()
        assert b.erreichbar and b.steuerbar
        m = {x.schluessel: x for x in b.modelle}
        assert m["qwen/qwen3-next-80b"].geladen and m["qwen/qwen3-next-80b"].parameter_mrd == 80 and m["qwen/qwen3-next-80b"].plaetze == 4
        assert m["text-embedding-bge-m3"].einbettung and m["text-embedding-bge-m3"].faehigkeiten == {F.EINBETTUNG}
        assert F.BILD_BESCHREIBEN in m["zai-org/glm-4.6v-flash"].faehigkeiten and not m["zai-org/glm-4.6v-flash"].geladen
        assert m["zai-org/glm-4.6v-flash"].gb == 11.8

        instanz = await a.laden("zai-org/glm-4.6v-flash")
        assert instanz == "zai-org/glm-4.6v-flash"
        strom = await a.anfrage("/v1/chat/completions", {"model": instanz, "stream": True, "messages": [{"role": "user", "content": "hallo"}]})
        assert strom.status == 200
        zeilen = [z async for z in strom.zeilen() if z.startswith(b"data: ")]
        await strom.schliessen()
        assert zeilen[-1] == b"data: [DONE]" and json.loads(zeilen[-2][6:])["usage"]["completion_tokens"] == 5

        await a.entladen(instanz)
        assert not {x.schluessel: x for x in (await a.zustand()).modelle}["zai-org/glm-4.6v-flash"].geladen
        await a.schliessen()


async def test_speichermangel_ist_wiederholbar():
    app = schein_laeufer()
    app.state.lage.speicher_gb = 50.0
    async with laufend(app) as adresse:
        a = OpenAIKompatibel(adresse)
        try:
            await a.laden("google/gemma-4-26b-a4b-qat")
            raise AssertionError("hätte abgelehnt werden müssen")
        except DienstFehler as f:
            assert f.grund == "modell_passt_nicht" and f.wiederholbar and "insufficient" in f.meldung
        await a.schliessen()


async def test_rueckfall_auf_openai_liste():
    app = FastAPI()

    @app.get("/v1/models")
    async def liste():
        return {"data": [{"id": "qwen3.6-35b"}, {"id": "text-embedding-3"}]}

    async with laufend(app) as adresse:
        a = OpenAIKompatibel(adresse)
        b = await a.zustand()
        assert b.erreichbar and not b.steuerbar and "Laden und Entladen übernimmt der Dienst" in b.meldung
        assert all(m.geladen for m in b.modelle) and {m.schluessel for m in b.modelle if m.einbettung} == {"text-embedding-3"}
        await a.schliessen()


async def test_nicht_erreichbar():
    a = OpenAIKompatibel("http://127.0.0.1:9", verbindung_s=0.5)
    b = await a.zustand()
    assert not b.erreichbar and "nicht erreichbar" in b.meldung
    await a.schliessen()
