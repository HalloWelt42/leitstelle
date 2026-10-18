"""Schreibfolge: Schreibzugriffe auf die Ablage nacheinander, in der Reihenfolge, in der sie anfallen.

Der Betrieb ändert seinen Zustand synchron und speichert im Hintergrund, damit kein Aufruf auf die Datenbank
wartet. Laufen zwei solche Schreibungen gleichzeitig, kann die ältere die neuere überholen oder beide lesen
denselben Stand und eine scheitert am doppelten Schlüssel (Vorfall vom 18.10.2026: Anlegen und Abschließen
eines kurzen Auftrags, der Endzustand ging verloren). Darum gibt es genau eine Folge, die abarbeitet, was ihr
übergeben wird; wer etwas einreiht, wartet nicht darauf.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Coroutine
from typing import Any

log = logging.getLogger("leitstelle.betrieb")


class Schreibfolge:
    def __init__(self) -> None:
        self._offen: deque[Coroutine[Any, Any, Any]] = deque()
        self._aufgabe: asyncio.Task | None = None

    def einreihen(self, schreiben: Coroutine[Any, Any, Any]) -> None:
        """Hinten anstellen; die Folge startet von selbst, wenn sie gerade ruht."""
        self._offen.append(schreiben)
        if self._aufgabe is None or self._aufgabe.done():
            self._aufgabe = asyncio.create_task(self._abarbeiten(), name="leitstelle-schreibfolge")

    async def _abarbeiten(self) -> None:
        while self._offen:
            schreiben = self._offen.popleft()
            try:
                await schreiben
            except Exception as fehler:    # eine gescheiterte Schreibung hält die folgenden nicht auf
                log.error("Schreiben in die Ablage gescheitert: %r", fehler)

    async def leeren(self) -> None:
        """Wartet, bis alles Eingereihte geschrieben ist (beim Beenden, in Tests)."""
        while self._aufgabe is not None and not self._aufgabe.done():
            await asyncio.shield(self._aufgabe)
