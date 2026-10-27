"""Schein-Bilddienst im üblichen Bildformat: bildet die Schnittstelle eines Bildwerk-Dienstes nach (Modell wie MOSS-Image),
ohne ein Bild zu rechnen.

`POST /v1/images/generations` prüft wie der echte Dienst (`model` muss das Modell oder die Kennung des Dienstes nennen,
sonst 409; Größe und Schritte nach dem Steckbrief, sonst 400; Form 422; vor dem Ende des Ladens 503; eine Beschreibung mit
"Fehler beim Rechnen" endet mit 500) und "rechnet"
`rechenzeit_s`, während er auf das Schließen der Verbindung achtet: geht der Aufrufer, endet die Rechnung (vermerkt in
`lage.abgebrochen`, Antwort 499). Die Bilder sind echte PNG mit einem Bildpunkt, dessen Farbe nur aus Beschreibung,
Startwert, Größe und Schritten folgt; Bild i rechnet mit seed + i. `POST /v1/images/edits` antwortet 501, `GET /v1/models`
liefert den Steckbrief, `GET /gesundheit` 200 bei bereit, sonst 503, `GET /lage` was er gesehen hat (für Tests).

Läuft auch als eigener Prozess (für den Maschinenraum): `python bilddienst.py <port> [rechenzeit_s] [startzeit_s]`.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import struct
import sys
import time
import zlib
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

KENNUNG = "moss-image"
DIENST = "bildwerk-moss-image"
NAME = "MOSS-Image-SFT"
ALIASE = ["OpenMOSS-Team/MOSS-Image-SFT"]
STECKBRIEF = {
    "kennung": KENNUNG, "name": NAME, "aliase": ALIASE,
    "zweck": "Bilder aus Text: lange Beschreibungen, Schrift im Bild (Englisch und Chinesisch), Anordnung per JSON",
    "faehigkeiten": ["bild_erzeugen"], "kann_bearbeiten": False, "bearbeiten_grund": "kein Bearbeiten im Schein",
    "eignung": ["gruendlich"], "sprachen": ["en", "zh"], "parameter_mrd": 4.9, "textkodierer": "Qwen3.5-9B", "lizenz": "Apache-2.0",
    "erschienen": "2026-10-16",
    "groessen": {"raster": 16, "kante_min": 256, "kante_max": 2048, "pixel_min": 512 * 512, "pixel_max": 2048 * 2048, "vorgabe": "1024x1024",
                 "empfohlen": ["1024x1024", "1344x768", "768x1344"]},
    "schritte": {"vorgabe": 50, "kleinste": 1, "groesste": 218}, "guidance": 3.0, "beschreibung_max_token": 4096,
    "quelle": {"repo": "OpenMOSS-Team/MOSS-Image-SFT", "revision": "schein"}, "quantisierung": "8bit",
    "rechenwerk": {"name": "mflux", "fassung": "schein"}, "anzahl_max": 4,
}


def png(farbe: bytes) -> bytes:
    """Ein PNG mit einem Bildpunkt in der Farbe (drei Byte)."""
    def block(art: bytes, daten: bytes) -> bytes:
        return struct.pack(">I", len(daten)) + art + daten + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + block(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + block(b"IDAT", zlib.compress(b"\x00" + farbe[:3])) + block(b"IEND", b""))


class Anfrage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str = Field(min_length=1)
    size: str | None = None
    n: int = Field(default=1, ge=1, le=4)
    seed: int | None = Field(default=None, ge=0)
    steps: int | None = None
    model: str | None = None
    response_format: str = "b64_json"


@dataclass
class Lage:
    rechenzeit_s: float = 0.05
    bereit_ab_s: float = 0.0                      # monotone Zeit, ab der das Modell geladen ist
    anfragen: list[dict] = field(default_factory=list)
    modelle_gelesen: int = 0
    laufend: int = 0
    abgebrochen: int = 0
    fertig: int = 0


def schein_bilddienst(rechenzeit_s: float = 0.05, startzeit_s: float = 0.0) -> FastAPI:
    app = FastAPI()
    lage = Lage(rechenzeit_s=rechenzeit_s, bereit_ab_s=time.monotonic() + startzeit_s)
    app.state.lage = lage
    sperre = asyncio.Lock()                       # wie der echte Dienst: eine Rechnung zugleich

    def bereit() -> bool:
        return time.monotonic() >= lage.bereit_ab_s

    @app.get("/gesundheit")
    async def gesundheit():
        return JSONResponse({"zustand": "bereit" if bereit() else "laedt"}, status_code=200 if bereit() else 503)

    @app.get("/lage")
    async def lage_lesen():
        """Für Tests, die den Dienst als eigenen Prozess starten: was er gesehen hat."""
        return {"anfragen": lage.anfragen, "modelle_gelesen": lage.modelle_gelesen, "laufend": lage.laufend, "abgebrochen": lage.abgebrochen,
                "fertig": lage.fertig}

    @app.get("/v1/models")
    async def modelle():
        lage.modelle_gelesen += 1
        return {"object": "list", "data": [{"id": KENNUNG, "object": "model", "created": 1792108800, "owned_by": "bildwerk",
                                            "steckbrief": {**STECKBRIEF, "zustand": "bereit" if bereit() else "laedt"}}]}

    @app.post("/v1/images/edits")
    async def bearbeiten():
        raise HTTPException(501, f"{NAME} kann keine Bilder bearbeiten: kein Bearbeiten im Schein")

    @app.post("/v1/images/generations")
    async def erzeugen(anfrage: Anfrage, request: Request):
        lage.anfragen.append(anfrage.model_dump())
        if anfrage.model and anfrage.model not in (KENNUNG, NAME, *ALIASE, DIENST):
            raise HTTPException(409, f"Dieser Dienst hält {KENNUNG}; für {anfrage.model} den Dienst dieses Modells nehmen.")
        breite, hoehe = (int(k) for k in (anfrage.size or "1024x1024").split("x"))
        if breite % 16 or hoehe % 16 or not 512 * 512 <= breite * hoehe <= 2048 * 2048:
            raise HTTPException(400, f"Die Fläche muss zwischen 262144 und 4194304 Pixeln liegen, {breite}x{hoehe} hat {breite * hoehe}.")
        schritte = anfrage.steps if anfrage.steps is not None else 50
        if not 1 <= schritte <= 218:
            raise HTTPException(400, f"Schritte 1 bis 218, nicht {schritte}.")
        if not bereit():
            raise HTTPException(503, f"Modell {KENNUNG} ist nicht bereit (laedt)")
        if "Fehler beim Rechnen" in anfrage.prompt:
            raise HTTPException(500, "Speicher erschöpft")
        seed = anfrage.seed if anfrage.seed is not None else 7
        async with sperre:
            lage.laufend += 1
            beginn = time.monotonic()
            try:
                while time.monotonic() - beginn < lage.rechenzeit_s:
                    if await request.is_disconnected():
                        lage.abgebrochen += 1
                        return JSONResponse({"detail": "abgebrochen: Verbindung geschlossen"}, status_code=499)
                    await asyncio.sleep(0.02)
            finally:
                lage.laufend -= 1
        seeds = [seed + i for i in range(anfrage.n)]
        bilder = [png(hashlib.sha256(f"{anfrage.prompt}|{s}|{breite}x{hoehe}|{schritte}".encode()).digest()) for s in seeds]
        lage.fertig += 1
        return {"created": int(time.time()), "data": [{"b64_json": base64.b64encode(b).decode("ascii"), "revised_prompt": None} for b in bilder],
                "x-bildwerk": {"modell": KENNUNG, "seed": seeds[0], "seeds": seeds, "schritte": schritte, "groesse": f"{breite}x{hoehe}",
                               "dauer_ms": round(lage.rechenzeit_s * 1000)}}

    return app


if __name__ == "__main__":
    import uvicorn

    port = int(sys.argv[1])
    rechenzeit = float(sys.argv[2]) if len(sys.argv) > 2 else 0.05
    startzeit = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    uvicorn.run(schein_bilddienst(rechenzeit, startzeit), host="127.0.0.1", port=port, log_level="warning")
