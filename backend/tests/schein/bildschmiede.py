"""Schein-Bildschmiede: bildet die Schnittstelle von ComfyUI nach, soweit der Bildablauf der Leitstelle sie nutzt.

`POST /prompt` nimmt einen Arbeitsgraphen an und rechnet ihn nach `rechenzeit_s`; danach führt `GET /history/<kennung>`
ihn mit den Bildern, die `GET /view` liefert. Die Bilder sind echte PNG (1 mal 1 Bildpunkt), deren Farbe nur aus
Beschreibung, Startwert, Größe und Stelle im Stapel folgt: gleiche Eingabe, gleiches Bild. `POST /queue` (delete) und
`POST /interrupt` (prompt_id) tragen einen Auftrag aus. Ein Checkpoint, den es nicht gibt, gibt 400 wie bei ComfyUI;
eine Beschreibung mit "Fehler beim Rechnen" endet als execution_error.

Läuft auch als eigener Prozess (für den Maschinenraum): `python bildschmiede.py <port> [rechenzeit_s] [startzeit_s]`.
"""

from __future__ import annotations

import asyncio
import hashlib
import struct
import sys
import zlib
from dataclasses import dataclass, field
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

CHECKPOINTS = {"flux1-schnell-fp8.safetensors"}


def png(farbe: bytes) -> bytes:
    """Ein PNG mit einem Bildpunkt in der Farbe (drei Byte)."""
    def block(art: bytes, daten: bytes) -> bytes:
        return struct.pack(">I", len(daten)) + art + daten + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + block(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + block(b"IDAT", zlib.compress(b"\x00" + farbe[:3])) + block(b"IEND", b""))


@dataclass
class Lage:
    rechenzeit_s: float = 0.05
    graphen: list[dict] = field(default_factory=list)
    verlauf: dict[str, dict] = field(default_factory=dict)
    dateien: dict[str, bytes] = field(default_factory=dict)
    aufgaben: dict[str, asyncio.Task] = field(default_factory=dict)
    ausgetragen: list[str] = field(default_factory=list)
    unterbrochen: list[str] = field(default_factory=list)


def schein_bildschmiede(rechenzeit_s: float = 0.05) -> FastAPI:
    app = FastAPI()
    lage = Lage(rechenzeit_s=rechenzeit_s)
    app.state.lage = lage

    async def rechnen(kennung: str, graph: dict) -> None:
        await asyncio.sleep(lage.rechenzeit_s)
        text = graph["2"]["inputs"]["text"]
        if "Fehler beim Rechnen" in text:
            lage.verlauf[kennung] = {"outputs": {}, "status": {"status_str": "error", "completed": False, "messages": [
                ["execution_start", {}], ["execution_error", {"node_type": "KSampler", "exception_message": "Speicher erschöpft"}]]}}
            return
        latent, sampler = graph["4"]["inputs"], graph["5"]["inputs"]
        bilder = []
        for i in range(latent["batch_size"]):
            farbe = hashlib.sha256(f"{text}|{sampler['seed']}|{latent['width']}x{latent['height']}|{i}".encode()).digest()
            name = f"{graph['7']['inputs']['filename_prefix']}_{uuid4().hex[:8]}.png"
            lage.dateien[name] = png(farbe)
            bilder.append({"filename": name, "subfolder": "", "type": "output"})
        lage.verlauf[kennung] = {"outputs": {"7": {"images": bilder}}, "status": {"status_str": "success", "completed": True, "messages": []}}

    @app.post("/prompt")
    async def einreihen(request: Request):
        graph = (await request.json())["prompt"]
        lage.graphen.append(graph)
        if graph["1"]["inputs"]["ckpt_name"] not in CHECKPOINTS:
            return JSONResponse({"error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed validation"},
                                 "node_errors": {"1": {"class_type": "CheckpointLoaderSimple", "errors": [
                                     {"message": "Value not in list", "details": f"ckpt_name: '{graph['1']['inputs']['ckpt_name']}' not in list"}]}}},
                                status_code=400)
        kennung = uuid4().hex
        lage.aufgaben[kennung] = asyncio.create_task(rechnen(kennung, graph))
        return {"prompt_id": kennung, "number": len(lage.graphen), "node_errors": {}}

    @app.get("/history/{kennung}")
    async def verlauf(kennung: str):
        return {kennung: lage.verlauf[kennung]} if kennung in lage.verlauf else {}

    @app.get("/view")
    async def ansehen(filename: str, subfolder: str = "", type: str = "output"):
        if filename not in lage.dateien:
            return Response(status_code=404)
        return Response(lage.dateien[filename], media_type="image/png")

    @app.post("/queue")
    async def warteschlange(request: Request):
        for kennung in (await request.json()).get("delete") or []:
            lage.ausgetragen.append(kennung)
        return {}

    @app.post("/interrupt")
    async def unterbrechen(request: Request):
        kennung = (await request.json()).get("prompt_id")
        if kennung in lage.aufgaben and not lage.aufgaben[kennung].done():
            lage.aufgaben[kennung].cancel()
            lage.unterbrochen.append(kennung)
        return {}

    return app


if __name__ == "__main__":
    import time

    import uvicorn

    port = int(sys.argv[1])
    rechenzeit = float(sys.argv[2]) if len(sys.argv) > 2 else 0.05
    if len(sys.argv) > 3:
        time.sleep(float(sys.argv[3]))      # Startzeit wie beim Laden des Checkpoints
    uvicorn.run(schein_bildschmiede(rechenzeit), host="127.0.0.1", port=port, log_level="warning")
