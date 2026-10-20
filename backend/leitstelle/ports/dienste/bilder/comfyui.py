"""Bildablauf für eine Bildschmiede mit ComfyUI-Schnittstelle.

Der Ablauf ist ein Arbeitsgraph: Checkpoint laden, Beschreibung kodieren (positiv und leer als negativ), leeres Latent
in der gewünschten Größe mit der Anzahl als Stapel, Sampler mit festem Startwert, dekodieren, speichern. Eingereiht
wird mit `POST /prompt`; fertig ist der Auftrag, sobald `GET /history/<kennung>` ihn führt; die Bilder kommen über
`GET /view`. Gleicher Startwert, gleiche Beschreibung, Größe und Anzahl ergeben dieselben Bilder.

Wird der Auftrag in der Leitstelle abgebrochen, nimmt der Ablauf ihn aus der Warteschlange der Bildschmiede und
unterbricht ihn, wenn er schon rechnet (nur diesen, nicht einen anderen).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import uuid4

from pydantic import BaseModel, Field

from ..schnittstelle import DienstFehler, Durchleitung
from .schnittstelle import Bildauftrag, Bildergebnis, Senden

log = logging.getLogger("leitstelle.bilder")

AUFRAEUMEN_S = 5.0                    # so lange darf das Austragen eines abgebrochenen Auftrags dauern


class ComfyAblauf(BaseModel):
    """Einstellung des Ablaufs (Umgebung `LEITSTELLE_BILDABLAEUFE`, je Dienst)."""

    art: Literal["comfyui"] = "comfyui"
    checkpoint: str = Field(default="flux1-schnell-fp8.safetensors", description="Checkpoint mit Textkodierer und VAE in einer Datei")
    schritte: int = Field(default=4, ge=1, le=200)
    cfg: float = Field(default=1.0, ge=0.0, le=30.0)
    sampler: str = "euler"
    scheduler: str = "simple"
    ablage_praefix: str = Field(default="leitstelle", description="Vorsilbe der gespeicherten Bilder im Ausgabeordner der Bildschmiede")
    abfrage_s: float = Field(default=0.5, gt=0.0, description="Abstand, in dem der Verlauf nach dem fertigen Auftrag gefragt wird")


def arbeitsgraph(e: ComfyAblauf, auftrag: Bildauftrag) -> dict[str, Any]:
    """Der Graph im API-Format von ComfyUI: Knoten nach Kennung, Eingänge als Werte oder [Knoten, Ausgang]."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": e.checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": auftrag.beschreibung, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": auftrag.breite, "height": auftrag.hoehe, "batch_size": auftrag.anzahl}},
        "5": {"class_type": "KSampler", "inputs": {"seed": auftrag.seed, "steps": e.schritte, "cfg": e.cfg, "sampler_name": e.sampler,
                                                   "scheduler": e.scheduler, "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0],
                                                   "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": e.ablage_praefix, "images": ["6", 0]}},
    }


def _fehlertext(daten: Any) -> str:
    """Meldung der Bildschmiede in einem Satz: Fehler beim Einreihen (`error`, `node_errors`) oder beim Rechnen."""
    if not isinstance(daten, dict):
        return str(daten)[:500]
    teile = []
    fehler = daten.get("error")
    if isinstance(fehler, dict):
        teile.append(str(fehler.get("message") or fehler.get("type") or fehler))
    elif fehler:
        teile.append(str(fehler))
    for knoten in (daten.get("node_errors") or {}).values():
        for f in knoten.get("errors") or []:
            teile.append(f"{knoten.get('class_type', '')}: {f.get('message', '')} {f.get('details', '')}".strip())
    return "; ".join(teile)[:500] or json.dumps(daten, ensure_ascii=False)[:500]


class Comfy:
    def __init__(self, einstellung: ComfyAblauf) -> None:
        self.e = einstellung

    async def erzeugen(self, senden: Senden, auftrag: Bildauftrag) -> Bildergebnis:
        kennung = await self._einreihen(senden, auftrag)
        try:
            bilder = await self._abwarten(senden, kennung)
        except asyncio.CancelledError:
            await self._austragen(senden, kennung)
            raise
        return Bildergebnis(bilder=[await self._holen(senden, b) for b in bilder], seed=auftrag.seed)

    async def _anfrage(self, senden: Senden, methode: str, pfad: str, koerper: Any = None, abfrage: str = "") -> tuple[int, bytes]:
        inhalt = json.dumps(koerper).encode() if koerper is not None else b""
        kopf = {"content-type": "application/json"} if koerper is not None else {}
        strom = await senden(Durchleitung(methode=methode, pfad=pfad, abfrage=abfrage, kopf=kopf, inhalt=inhalt))
        try:
            return strom.status, await strom.lesen()
        finally:
            await strom.schliessen()

    async def _json(self, senden: Senden, methode: str, pfad: str, koerper: Any = None) -> Any:
        status, roh = await self._anfrage(senden, methode, pfad, koerper)
        try:
            daten = json.loads(roh) if roh else {}
        except ValueError:
            daten = roh.decode("utf-8", "replace")
        if status >= 400:
            raise DienstFehler("dienst_fehler", f"Bildschmiede antwortet mit {status}: {_fehlertext(daten)}")
        return daten

    async def _einreihen(self, senden: Senden, auftrag: Bildauftrag) -> str:
        daten = await self._json(senden, "POST", "prompt", {"prompt": arbeitsgraph(self.e, auftrag), "client_id": uuid4().hex})
        kennung = daten.get("prompt_id") if isinstance(daten, dict) else None
        if not kennung:
            raise DienstFehler("dienst_fehler", f"Bildschmiede hat den Auftrag nicht eingereiht: {_fehlertext(daten)}")
        return str(kennung)

    async def _abwarten(self, senden: Senden, kennung: str) -> list[dict[str, str]]:
        """Bis der Verlauf den Auftrag führt; dann die Bilder aller Ausgaben oder die Fehlermeldung."""
        while True:
            daten = await self._json(senden, "GET", f"history/{kennung}")
            eintrag = daten.get(kennung) if isinstance(daten, dict) else None
            if eintrag:
                stand = eintrag.get("status") or {}
                if stand.get("status_str") == "error":
                    raise DienstFehler("dienst_fehler", f"Bildschmiede: {self._rechenfehler(stand)}")
                bilder = [b for ausgabe in (eintrag.get("outputs") or {}).values() for b in ausgabe.get("images") or []]
                if not bilder:
                    raise DienstFehler("dienst_fehler", "Bildschmiede hat den Auftrag ohne Bild beendet.")
                return bilder
            await asyncio.sleep(self.e.abfrage_s)

    @staticmethod
    def _rechenfehler(stand: dict[str, Any]) -> str:
        for art, inhalt in stand.get("messages") or []:
            if art == "execution_error" and isinstance(inhalt, dict):
                return f"{inhalt.get('node_type', '')}: {inhalt.get('exception_message', '')}".strip(": ")[:500]
        return "Fehler beim Rechnen"

    async def _holen(self, senden: Senden, bild: dict[str, str]) -> bytes:
        abfrage = urlencode({"filename": bild.get("filename", ""), "subfolder": bild.get("subfolder", ""), "type": bild.get("type", "output")})
        status, roh = await self._anfrage(senden, "GET", "view", abfrage=abfrage)
        if status >= 400:
            raise DienstFehler("dienst_fehler", f"Bildschmiede liefert das Bild {bild.get('filename')} nicht ({status}).")
        return roh

    async def _austragen(self, senden: Senden, kennung: str) -> None:
        """Abgebrochen: aus der Warteschlange nehmen und, falls er schon rechnet, genau diesen Auftrag unterbrechen."""
        try:
            await asyncio.wait_for(asyncio.gather(self._json(senden, "POST", "queue", {"delete": [kennung]}),
                                                  self._json(senden, "POST", "interrupt", {"prompt_id": kennung})), AUFRAEUMEN_S)
        except (DienstFehler, TimeoutError, asyncio.CancelledError) as fehler:
            log.warning("Abgebrochenen Bildauftrag %s nicht ausgetragen: %r", kennung, fehler)
