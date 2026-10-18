"""Schein-Läufer: bildet die Schnittstelle des Modell-Läufers nach, wie sie am echten Gerät gemessen wurde.

Native Schnittstelle `/api/v1/models` mit Laden (Speichergrenze, Ladezeit) und Entladen per Instanz,
OpenAI-Schnittstelle `/v1/chat/completions` (mit und ohne Strom) und `/v1/embeddings`, dazu `/schein/sprechen`
wie ein Dienst mit eigener Schnittstelle für die Dienstfassade. Anders als der echte Läufer lädt er nie von
selbst: wer ein nicht geladenes Modell anspricht, bekommt 400. So fällt auf, wenn die Leitstelle das Laden vergisst.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


@dataclass
class ScheinModell:
    schluessel: str
    name: str
    typ: str = "llm"                 # llm, vlm (über vision), embedding
    gb: float = 10.0
    params: str | None = "27B"
    vision: bool = False
    instanzen: list[str] = field(default_factory=list)


@dataclass
class Lage:
    modelle: dict[str, ScheinModell]
    speicher_gb: float = 100.0       # was der Läufer insgesamt laden lässt
    ladezeit_s: float = 0.05
    entladezeit_s: float = 0.0       # bis der Speicher wirklich frei ist
    stueck_pause_s: float = 0.01
    stuecke: int = 5
    kopf_pause_s: float = 0.0        # /schein/sprechen: Rechenzeit bis zum Antwortkopf
    parallel: int = 4
    anfragen: list[dict] = field(default_factory=list)
    gleichzeitig: int = 0
    gleichzeitig_hoechst: int = 0
    abgebrochen: int = 0
    ladevorgaenge: list[str] = field(default_factory=list)
    entladevorgaenge: list[str] = field(default_factory=list)

    def belegt(self) -> float:
        return sum(m.gb for m in self.modelle.values() if m.instanzen)

    def modell_der_instanz(self, kennung: str) -> ScheinModell | None:
        for m in self.modelle.values():
            if kennung == m.schluessel or kennung in m.instanzen:
                return m
        return None


def standard_modelle() -> dict[str, ScheinModell]:
    ms = [
        ScheinModell("qwen/qwen3-next-80b", "Qwen3 Next 80B", gb=44.9, params="80B", instanzen=["qwen/qwen3-next-80b"]),
        ScheinModell("text-embedding-bge-m3", "Bge M3", typ="embedding", gb=0.6, params="567M", instanzen=["text-embedding-bge-m3"]),
        ScheinModell("zai-org/glm-4.6v-flash", "Glm 4.6v Flash", gb=11.8, params="9B", vision=True),
        ScheinModell("google/gemma-4-26b-a4b-qat", "Gemma 4 26B A4B QAT", gb=15.6, params="26B", vision=True),
        ScheinModell("qwen/qwen3-coder-next", "Qwen3 Coder Next", gb=44.9, params="80B"),
    ]
    return {m.schluessel: m for m in ms}


def schein_laeufer(lage: Lage | None = None) -> FastAPI:
    app = FastAPI()
    app.state.lage = lage or Lage(modelle=standard_modelle())

    def L() -> Lage:
        return app.state.lage

    @app.get("/api/v1/models")
    async def modelle():
        aus = []
        for m in L().modelle.values():
            aus.append({"key": m.schluessel, "type": "embedding" if m.typ == "embedding" else "llm", "display_name": m.name,
                        "params_string": m.params, "size_bytes": int(m.gb * 1e9), "max_context_length": 32768,
                        "capabilities": None if m.typ == "embedding" else {"vision": m.vision, "trained_for_tool_use": True},
                        "loaded_instances": [{"id": i, "config": {"context_length": 32768, "parallel": L().parallel}} for i in m.instanzen]})
        return {"models": aus}

    @app.post("/api/v1/models/load")
    async def laden(anfrage: Request):
        koerper = await anfrage.json()
        m = L().modelle.get(koerper.get("model", ""))
        if m is None:
            return JSONResponse({"error": {"message": f"model {koerper.get('model')} not found"}}, status_code=404)
        if m.instanzen:
            return {"instance_id": m.instanzen[0], "status": "loaded", "load_time_seconds": 0}
        if L().belegt() + m.gb > L().speicher_gb:
            return JSONResponse({"error": {"message": "Model loading was stopped due to insufficient system resources"}}, status_code=400)
        start = time.monotonic()
        await asyncio.sleep(L().ladezeit_s)
        m.instanzen.append(m.schluessel)
        L().ladevorgaenge.append(m.schluessel)
        return {"instance_id": m.schluessel, "status": "loaded", "load_time_seconds": time.monotonic() - start}

    @app.post("/api/v1/models/unload")
    async def entladen(anfrage: Request):
        kennung = (await anfrage.json()).get("instance_id", "")
        m = L().modell_der_instanz(kennung)
        if m is None or kennung not in m.instanzen:
            return JSONResponse({"error": {"message": f"instance {kennung} not loaded"}}, status_code=404)
        await asyncio.sleep(L().entladezeit_s)
        m.instanzen.remove(kennung)
        L().entladevorgaenge.append(m.schluessel)
        return {"instance_id": kennung}

    @app.get("/v1/models")
    async def openai_modelle():
        return {"object": "list", "data": [{"id": m.schluessel, "object": "model", "owned_by": "schein"} for m in L().modelle.values()]}

    @app.post("/v1/chat/completions")
    async def chat(anfrage: Request):
        koerper = await anfrage.json()
        L().anfragen.append(koerper)
        m = L().modell_der_instanz(koerper.get("model", ""))
        if m is None or not m.instanzen:
            return JSONResponse({"error": {"message": f"Model {koerper.get('model')} is not loaded"}}, status_code=400)
        modell = koerper["model"]
        stuecke = [f"Stück{i} " for i in range(L().stuecke)]

        if not koerper.get("stream"):
            L().gleichzeitig += 1
            L().gleichzeitig_hoechst = max(L().gleichzeitig_hoechst, L().gleichzeitig)
            try:
                await asyncio.sleep(L().stueck_pause_s * len(stuecke))
            finally:
                L().gleichzeitig -= 1
            return {"id": "chatcmpl-schein", "object": "chat.completion", "model": modell,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(stuecke)}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": len(stuecke), "total_tokens": 7 + len(stuecke)}}

        async def strom():
            L().gleichzeitig += 1
            L().gleichzeitig_hoechst = max(L().gleichzeitig_hoechst, L().gleichzeitig)
            fertig = False
            try:
                for s in stuecke:
                    await asyncio.sleep(L().stueck_pause_s)
                    yield "data: " + json.dumps({"id": "chatcmpl-schein", "object": "chat.completion.chunk", "model": modell,
                                                 "choices": [{"index": 0, "delta": {"content": s}, "finish_reason": None}]}) + "\n\n"
                yield "data: " + json.dumps({"id": "chatcmpl-schein", "object": "chat.completion.chunk", "model": modell,
                                             "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                                             "usage": {"prompt_tokens": 7, "completion_tokens": len(stuecke), "total_tokens": 7 + len(stuecke)}}) + "\n\n"
                yield "data: [DONE]\n\n"
                fertig = True
            finally:
                L().gleichzeitig -= 1
                if not fertig:
                    L().abgebrochen += 1

        return StreamingResponse(strom(), media_type="text/event-stream")

    @app.api_route("/schein/sprechen", methods=["GET", "POST"])
    async def sprechen():
        """Wie ein Dienst mit eigener Schnittstelle (Sprache): rechnet `kopf_pause_s` vor dem Antwortkopf, liefert
        dann `stuecke` Binärstücke im Abstand von `stueck_pause_s`; eine abgerissene Antwort zählt in `abgebrochen`."""
        await asyncio.sleep(L().kopf_pause_s)

        async def ton():
            fertig = False
            try:
                for _ in range(L().stuecke):
                    await asyncio.sleep(L().stueck_pause_s)
                    yield b"\x00\x01" * 512
                fertig = True
            finally:
                if not fertig:
                    L().abgebrochen += 1

        return StreamingResponse(ton(), media_type="audio/wav")

    @app.post("/v1/embeddings")
    async def einbettung(anfrage: Request):
        koerper = await anfrage.json()
        L().anfragen.append(koerper)
        m = L().modell_der_instanz(koerper.get("model", ""))
        if m is None or not m.instanzen:
            return JSONResponse({"error": {"message": f"Model {koerper.get('model')} is not loaded"}}, status_code=400)
        texte = koerper.get("input", [])
        texte = [texte] if isinstance(texte, str) else texte
        return {"object": "list", "model": koerper["model"], "data": [{"object": "embedding", "index": i, "embedding": [0.1, 0.2, 0.3]} for i, _ in enumerate(texte)],
                "usage": {"prompt_tokens": len(texte), "total_tokens": len(texte)}}

    return app
