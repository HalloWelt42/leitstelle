"""Start des Kern-Dienstes: `python -m leitstelle` (Einstellungen über LEITSTELLE_*)."""

from __future__ import annotations

import logging
from typing import Any

import uvicorn

from .api.app import erstellen
from .konfig import Konfig


def serveroptionen(konfig: Konfig) -> dict[str, Any]:
    """Optionen für uvicorn. Weiterleitungsköpfe gelten nur vom eingestellten Vorschaltdienst; ohne ihn nie, sonst
    könnte jeder Aufrufer seine Herkunft selbst behaupten."""
    optionen: dict[str, Any] = {"host": konfig.host, "port": konfig.port, "log_level": "info"}
    if konfig.vorschaltung:
        return {**optionen, "proxy_headers": True, "forwarded_allow_ips": list(konfig.vorschaltung)}
    return {**optionen, "proxy_headers": False}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    konfig = Konfig()
    uvicorn.run(erstellen(konfig), **serveroptionen(konfig))


if __name__ == "__main__":
    main()
