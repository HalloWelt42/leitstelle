"""Start des Kern-Dienstes: `python -m leitstelle` (Einstellungen über LEITSTELLE_*)."""

from __future__ import annotations

import logging

import uvicorn

from .api.app import erstellen
from .konfig import Konfig


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    konfig = Konfig()
    uvicorn.run(erstellen(konfig), host=konfig.host, port=konfig.port, log_level="info", proxy_headers=False)


if __name__ == "__main__":
    main()
