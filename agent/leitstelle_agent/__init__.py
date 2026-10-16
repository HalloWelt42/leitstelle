"""Knoten-Agent der Leitstelle.

Die Fassung kommt aus der Leitstelle: beim Ausliefern legt sie `VERSION` ins Paket. Im Quellbaum gilt
`version.json` im Wurzelordner.
"""

from __future__ import annotations

import json
from pathlib import Path


def _fassung() -> str:
    hier = Path(__file__).resolve().parent
    datei = hier / "VERSION"
    if datei.is_file():
        return datei.read_text(encoding="utf-8").strip()
    quelle = hier.parents[1] / "version.json"
    if quelle.is_file():
        return json.loads(quelle.read_text(encoding="utf-8"))["version"]
    return "0.0.0"


__version__ = _fassung()
