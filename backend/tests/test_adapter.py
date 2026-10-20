"""Adapter openai_kompatibel gegen den Schein-Läufer: Zustand lesen, laden, entladen, durchleiten,
Rückfall auf die reine OpenAI-Liste, nicht erreichbar."""

import json

from fastapi import FastAPI

from leitstelle.kern.werte import Faehigkeit as F
from leitstelle.ports.dienste import DienstFehler
from leitstelle.ports.dienste.openai_kompatibel import ExternOpenAI, OpenAIKompatibel, _milliarden, _milliarden_im_namen

from schein.laeufer import schein_laeufer
from schein.server import laufend


def test_einbettung_im_mlx_format_wird_am_namen_erkannt():
    """L9: der Läufer meldet Einbettungsmodelle im MLX-Format als `llm` mit Werkzeugen (aufgezeichnet am 20.10.2026);
    sie sind trotzdem nur Einbettung und geschützt, nie ein Gesprächsmodell."""
    roh = {"type": "llm", "publisher": "mlx-community", "key": "qwen3-embedding-8b", "display_name": "Qwen3 Embedding 8B", "architecture": "qwen3",
           "quantization": {"name": "MXFP8", "bits_per_weight": 8}, "size_bytes": 7818384967, "params_string": "8B", "loaded_instances": [],
           "max_context_length": 40960, "format": "mlx", "capabilities": {"vision": False, "trained_for_tool_use": True}, "description": None}
    m = OpenAIKompatibel._nativ(roh)
    assert m.einbettung and m.faehigkeiten == {F.EINBETTUNG}
    gespraech = OpenAIKompatibel._nativ({**roh, "key": "qwen/qwen3-next-80b", "display_name": "Qwen3 Next 80B"})
    assert not gespraech.einbettung and gespraech.faehigkeiten == {F.TEXT, F.UEBERSETZEN, F.WERKZEUG}
    assert OpenAIKompatibel._einfach({"id": "nomic-embed-text"}).einbettung and not OpenAIKompatibel._einfach({"id": "gemma-3-27b"}).einbettung


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
        assert m["zai-org/glm-4.6v-flash"].gb == round(11.8e9 / 1024**3, 2)              # GB wie macOS: 1024^3 Byte

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


HETZNER_MODELLE = {"object": "list", "data": [
    {"id": "Qwen/Qwen3.6-35B-A3B", "object": "model", "owned_by": "hetzner", "root": "s3://models/qwen36-35b-a3b-fp8", "max_model_len": 262144},
    {"id": "Qwen/Qwen3.6-35B-A3B-FP8", "object": "model", "owned_by": "hetzner", "root": "s3://models/qwen36-35b-a3b-fp8", "max_model_len": 262144},
    {"id": "Qwen/Qwen3.8-27B", "object": "model", "owned_by": "hetzner", "root": "s3://models/qwen38-27b-fp8", "max_model_len": 262144},
    {"id": "Qwen3.8-27B", "object": "model", "owned_by": "hetzner", "root": "s3://models/qwen38-27b-fp8", "max_model_len": 262144}]}


async def test_externer_anbieter_wie_hetzner():
    """Antwort wie bei Hetzner gemessen (18.10.2026): je Modell zwei Namen mit gleichem root. Der Adapter fragt nur
    /v1/models (eine Anfrage, sie zählt für die Grenze), fasst Namen zu einem Modell zusammen und lädt nie."""
    app = FastAPI()
    gesehen: list[str] = []

    @app.middleware("http")
    async def mitschreiben(anfrage, weiter):
        gesehen.append(anfrage.url.path)
        return await weiter(anfrage)

    @app.get("/api/v1/models")
    async def liste():
        return HETZNER_MODELLE

    gezaehlt = []
    async with laufend(app) as adresse:
        a = ExternOpenAI(adresse + "/api/v1", "geheim", beim_senden=lambda: gezaehlt.append(1))
        b = await a.zustand()
        assert gesehen == ["/api/v1/models"] and len(gezaehlt) == 1
        assert b.erreichbar and not b.steuerbar
        m = {x.schluessel: x for x in b.modelle}
        assert set(m) == {"Qwen/Qwen3.6-35B-A3B", "Qwen/Qwen3.8-27B"}
        assert m["Qwen/Qwen3.8-27B"].instanzen == ["Qwen/Qwen3.8-27B", "Qwen3.8-27B"] and m["Qwen/Qwen3.8-27B"].kontext == 262144
        assert m["Qwen/Qwen3.6-35B-A3B"].parameter_mrd == 35 and m["Qwen/Qwen3.6-35B-A3B"].geladen
        try:
            await a.laden("Qwen/Qwen3.8-27B")
            raise AssertionError("ein externer Anbieter lädt selbst")
        except DienstFehler as f:
            assert f.grund == "nicht_steuerbar"
        await a.schliessen()


def test_parameterzahl_im_namen():
    assert _milliarden_im_namen("Qwen/Qwen3.6-35B-A3B") == 35 and _milliarden_im_namen("Qwen3.8-27B") == 27
    assert _milliarden_im_namen("text-embedding-bge-m3") is None
