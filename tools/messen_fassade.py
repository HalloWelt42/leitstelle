#!/usr/bin/env python3
"""Messpunkt Staffel 1: Was kostet die Durchleitung durch die Leitstelle?

Startet einen schnellen Schein-Läufer und einen frischen Kern als eigene Prozesse (eigener Datenordner),
richtet Rechner, Dienst und Anwendung über die Verwaltung ein und vergleicht dann direkt gegen den Läufer
mit "über die Fassade": Zeit bis zum ersten Stück, Gesamtzeit, Durchsatz bei gleichzeitigen Strömen.
Nichts Echtes wird berührt.

Aufruf aus der Projektwurzel:  backend/.venv/bin/python tools/messen_fassade.py [--laeufe 50] [--gleichzeitig 20]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

WURZEL = Path(__file__).resolve().parents[1]
PY = sys.executable
MODELL = "qwen/qwen3-next-80b"


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def warten_auf(url: str, sekunden: float = 30) -> None:
    async with httpx.AsyncClient() as c:
        for _ in range(int(sekunden * 10)):
            try:
                if (await c.get(url)).status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.1)
    raise SystemExit(f"{url} antwortet nicht")


async def ein_strom(c: httpx.AsyncClient, url: str, kopf: dict) -> tuple[float, float, int]:
    start = time.perf_counter()
    erstes = None
    stuecke = 0
    async with c.stream("POST", url, json={"model": MODELL, "stream": True, "messages": [{"role": "user", "content": "messen"}]}, headers=kopf) as r:
        r.raise_for_status()
        async for zeile in r.aiter_lines():
            if zeile.startswith("data: ") and zeile != "data: [DONE]":
                stuecke += 1
                if erstes is None:
                    erstes = time.perf_counter() - start
    return erstes or 0.0, time.perf_counter() - start, stuecke


async def reihe(url: str, kopf: dict, laeufe: int) -> dict:
    async with httpx.AsyncClient(timeout=None) as c:
        await ein_strom(c, url, kopf)                     # Aufwärmen
        werte = [await ein_strom(c, url, kopf) for _ in range(laeufe)]
    erste = [w[0] * 1000 for w in werte]
    gesamt = [w[1] * 1000 for w in werte]
    return {"erstes_median": statistics.median(erste), "erstes_p95": sorted(erste)[int(len(erste) * 0.95) - 1], "gesamt_median": statistics.median(gesamt)}


async def gleichzeitig(url: str, kopf: dict, n: int) -> dict:
    async with httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=n + 4)) as c:
        start = time.perf_counter()
        werte = await asyncio.gather(*(ein_strom(c, url, kopf) for _ in range(n)))
        dauer = time.perf_counter() - start
    stuecke = sum(w[2] for w in werte)
    return {"dauer_s": dauer, "stuecke_je_s": stuecke / dauer, "erstes_max": max(w[0] for w in werte) * 1000, "erstes_median": statistics.median(w[0] for w in werte) * 1000}


async def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--laeufe", type=int, default=50)
    a.add_argument("--gleichzeitig", type=int, default=20)
    a.add_argument("--stuecke", type=int, default=100)
    a.add_argument("--pause", type=float, default=0.002, help="Sekunden zwischen zwei Stücken des Schein-Läufers")
    arg = a.parse_args()

    p_laeufer, p_kern = freier_port(), freier_port()
    daten = tempfile.mkdtemp(prefix="leitstelle-messen-")
    umgebung = {**os.environ, "LEITSTELLE_DATEN": daten, "LEITSTELLE_PORT": str(p_kern), "LEITSTELLE_HOST": "127.0.0.1",
                "LEITSTELLE_OBERFLAECHE": str(Path(daten) / "keine-oberflaeche")}
    prozesse = [
        subprocess.Popen([PY, str(WURZEL / "tools" / "schein_laeufer.py"), "--port", str(p_laeufer), "--pause", str(arg.pause),
                          "--stuecke", str(arg.stuecke), "--ladezeit", "0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        subprocess.Popen([PY, "-m", "leitstelle"], cwd=WURZEL / "backend", env=umgebung, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    ]
    try:
        laeufer, kern = f"http://127.0.0.1:{p_laeufer}", f"http://127.0.0.1:{p_kern}"
        await warten_auf(f"{laeufer}/v1/models")
        await warten_auf(f"{kern}/gesundheit")
        async with httpx.AsyncClient(base_url=kern, timeout=30) as c:
            r = await c.post("/api/dienste", json={"adresse": laeufer, "plaetze": arg.gleichzeitig,
                                                   "neuer_knoten": {"name": "Messrechner", "adresse": "127.0.0.1", "speicher_gb": 128}})
            r.raise_for_status()
            schluessel = (await c.post("/api/anwendungen", json={"name": "Messung", "prioritaet": 2, "gleichzeitig": arg.gleichzeitig})).json()["schluessel"]
        kopf = {"Authorization": f"Bearer {schluessel}"}

        direkt = await reihe(f"{laeufer}/v1/chat/completions", {}, arg.laeufe)
        fassade = await reihe(f"{kern}/v1/chat/completions", kopf, arg.laeufe)
        d_viele = await gleichzeitig(f"{laeufer}/v1/chat/completions", {}, arg.gleichzeitig)
        f_viele = await gleichzeitig(f"{kern}/v1/chat/completions", kopf, arg.gleichzeitig)
    finally:
        for p in prozesse:
            p.terminate()
        for p in prozesse:
            p.wait(timeout=10)

    print(f"Rechner: {platform.node()} ({platform.machine()}), Python {platform.python_version()}, "
          f"{arg.laeufe} Läufe nacheinander, {arg.gleichzeitig} gleichzeitig, je {arg.stuecke} Stücke, Pause {arg.pause * 1000:.0f} ms\n")
    print("| Messung | direkt | über die Leitstelle | Aufschlag |")
    print("|---|---|---|---|")
    for name, schl in (("Erstes Stück, Median", "erstes_median"), ("Erstes Stück, 95. Perzentil", "erstes_p95"), ("Ganzer Strom, Median", "gesamt_median")):
        print(f"| {name} | {direkt[schl]:.1f} ms | {fassade[schl]:.1f} ms | {fassade[schl] - direkt[schl]:+.1f} ms |")
    print(f"| {arg.gleichzeitig} Ströme gleichzeitig, Gesamtdauer | {d_viele['dauer_s']:.2f} s | {f_viele['dauer_s']:.2f} s | {f_viele['dauer_s'] - d_viele['dauer_s']:+.2f} s |")
    print(f"| {arg.gleichzeitig} Ströme gleichzeitig, Stücke je Sekunde | {d_viele['stuecke_je_s']:.0f} | {f_viele['stuecke_je_s']:.0f} | {f_viele['stuecke_je_s'] / d_viele['stuecke_je_s'] * 100 - 100:+.0f} % |")
    print(f"| {arg.gleichzeitig} Ströme gleichzeitig, erstes Stück höchstens | {d_viele['erstes_max']:.1f} ms | {f_viele['erstes_max']:.1f} ms | {f_viele['erstes_max'] - d_viele['erstes_max']:+.1f} ms |")


if __name__ == "__main__":
    asyncio.run(main())
