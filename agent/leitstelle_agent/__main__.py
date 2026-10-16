"""Startpunkt: `python -m leitstelle_agent <agentenordner>` (Vorgabe ~/Leitstelle-Agent).

Mit `--liste` zeigt der Agent nur, welche Dienste er im Ordner findet und wie sie stehen, und beendet sich.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from . import __version__
from .kanal import Kanal
from .konfig import Agentenordner
from .messen import Messer
from .prozesse import Verwalter

log = logging.getLogger("leitstelle_agent")


async def laufen(ordner: Agentenordner) -> None:
    konfig = ordner.konfig()
    messer = Messer(konfig.takt_s, konfig.macmon)
    verwalter = Verwalter(ordner, konfig)
    log.info("Knoten-Agent %s in %s, Leitstelle %s", __version__, ordner.wurzel, konfig.leitstelle)
    halt = asyncio.Event()
    schleife = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        schleife.add_signal_handler(sig, halt.set)
    aufgaben = [asyncio.create_task(verwalter.schleife(), name="dienste"), asyncio.create_task(Kanal(ordner, konfig, verwalter, messer).schleife(), name="kanal")]
    await halt.wait()
    log.info("Agent wird beendet; die Dienste laufen weiter und werden beim nächsten Start wiedererkannt")
    for t in aufgaben:
        t.cancel()
    await asyncio.gather(*aufgaben, return_exceptions=True)
    await verwalter.beenden()
    messer.beenden()


async def liste(ordner: Agentenordner) -> None:
    verwalter = Verwalter(ordner, ordner.konfig())
    await verwalter.runde()
    for f in verwalter.ladefehler:
        print(f"FEHLER  {f.datei}: {f.meldung}")
    for b in verwalter.liste().dienste:
        soll = verwalter.stand.dienste[b.kennung].soll
        print(f"{b.zustand.value:9} {b.kennung:20} {b.gb:6.1f} GB  Port {b.port or '-':>5}  soll {soll.value if soll else '-':7} {b.meldung}")


def main() -> None:
    p = argparse.ArgumentParser(prog="leitstelle-agent", description="Knoten-Agent der Leitstelle")
    p.add_argument("ordner", nargs="?", default="~/Leitstelle-Agent", help="Agentenordner mit agent.toml, schluessel und dienste/")
    p.add_argument("--liste", action="store_true", help="nur den Stand der Dienste zeigen")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ordner = Agentenordner(Path(a.ordner))
    asyncio.run(liste(ordner) if a.liste else laufen(ordner))


if __name__ == "__main__":
    main()
