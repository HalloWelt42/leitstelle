#!/usr/bin/env python3
"""Schein-Läufer als eigener Dienst für Entwicklung und Vorführung (nie gegen echte Modelle).

Aufruf aus der Projektwurzel:
  backend/.venv/bin/python tools/schein_laeufer.py --port 8539 --pause 0.3 --stuecke 80 --speicher 100
Danach in der Leitstelle unter Anschluss hinzufügen die Adresse http://127.0.0.1:8539 eintragen.
"""

import argparse
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "tests"))
from schein.laeufer import Lage, schein_laeufer, standard_modelle  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=8539)
    p.add_argument("--pause", type=float, default=0.3, help="Sekunden je Stück eines Stroms")
    p.add_argument("--stuecke", type=int, default=80, help="Stücke je Antwort")
    p.add_argument("--ladezeit", type=float, default=4.0, help="Sekunden je Ladevorgang")
    p.add_argument("--speicher", type=float, default=100.0, help="GB, die der Läufer insgesamt laden lässt")
    a = p.parse_args()
    lage = Lage(modelle=standard_modelle(), speicher_gb=a.speicher, ladezeit_s=a.ladezeit, stueck_pause_s=a.pause, stuecke=a.stuecke)
    uvicorn.run(schein_laeufer(lage), host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
