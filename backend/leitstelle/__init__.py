"""Leitstelle: zentrale Vermittlung für KI-Dienste im Verbund.

Die Version steht nur in version.json im Projektwurzelordner (eine Wahrheit).
"""

from __future__ import annotations

import json
from pathlib import Path


def version() -> str:
    """Liest die Version aus version.json; fällt auf 0.0.0 zurück, wenn die Datei fehlt (Tests)."""
    datei = Path(__file__).resolve().parents[2] / "version.json"
    try:
        return str(json.loads(datei.read_text(encoding="utf-8"))["version"])
    except (OSError, KeyError, ValueError):
        return "0.0.0"


__version__ = version()
