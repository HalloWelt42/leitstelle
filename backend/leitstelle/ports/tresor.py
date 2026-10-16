"""Tresor: verschlüsselte Ablage von Schlüsseln und Zugängen (Fernet).

Der Tresorschlüssel liegt als Datei im Datenordner (nur für den Besitzer lesbar) und wird beim
ersten Start erzeugt. Ohne ihn sind die gespeicherten Geheimnisse nicht lesbar; die Sicherung des
Datenordners enthält ihn deshalb mit.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class TresorFehler(Exception):
    pass


class Tresor:
    def __init__(self, schluesseldatei: Path) -> None:
        schluesseldatei.parent.mkdir(parents=True, exist_ok=True)
        if not schluesseldatei.exists():
            schluesseldatei.write_bytes(Fernet.generate_key())
            os.chmod(schluesseldatei, 0o600)
        self._fernet = Fernet(schluesseldatei.read_bytes().strip())

    def verschluesseln(self, klartext: str) -> str:
        return self._fernet.encrypt(klartext.encode("utf-8")).decode("ascii")

    def entschluesseln(self, geheim: str) -> str:
        try:
            return self._fernet.decrypt(geheim.encode("ascii")).decode("utf-8")
        except InvalidToken as fehler:
            raise TresorFehler("Geheimnis passt nicht zum Tresorschlüssel") from fehler


def neuer_anwendungsschluessel() -> str:
    """Schlüssel für eine Anwendung: erkennbare Vorsilbe, 40 Hexzeichen Zufall."""
    return "ls_" + secrets.token_hex(20)


def fingerabdruck(schluessel: str) -> str:
    """Zum Nachschlagen ohne Entschlüsseln (Fassade prüft jeden Aufruf)."""
    return hashlib.sha256(schluessel.encode("utf-8")).hexdigest()
