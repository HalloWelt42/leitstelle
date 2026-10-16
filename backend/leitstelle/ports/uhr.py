"""Zeitquelle. Der Kern rechnet in Sekunden (float); im Betrieb sind das Sekunden seit 1970,
in Tests eine stellbare Uhr."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Protocol


class Uhr(Protocol):
    def jetzt(self) -> float: ...
    def stunde(self) -> int: ...


class Systemuhr:
    def jetzt(self) -> float:
        return time.time()

    def stunde(self) -> int:
        return datetime.now().hour


class Stelluhr:
    """Für Tests: läuft nur, wenn man sie stellt."""

    def __init__(self, start: float = 1_000_000.0, stunde: int = 12) -> None:
        self.zeit = start
        self._stunde = stunde

    def jetzt(self) -> float:
        return self.zeit

    def stunde(self) -> int:
        return self._stunde

    def vor(self, sekunden: float) -> None:
        self.zeit += sekunden
