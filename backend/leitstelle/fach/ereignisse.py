"""Ereignisbus: verteilt Umschläge an alle Abonnenten (Oberfläche, später Anwendungen über den Kanal).

Langsame Abonnenten verlieren die ältesten Ereignisse statt die Leitstelle aufzuhalten; der nächste
Lagebild-Umschlag ersetzt verpasste Zwischenstände.
"""

from __future__ import annotations

import asyncio

from ..protokoll.umschlag import Umschlag


class Ereignisbus:
    def __init__(self, puffer: int = 200) -> None:
        self._puffer = puffer
        self._abos: set[asyncio.Queue[Umschlag]] = set()

    def abonnieren(self) -> asyncio.Queue[Umschlag]:
        q: asyncio.Queue[Umschlag] = asyncio.Queue(maxsize=self._puffer)
        self._abos.add(q)
        return q

    def abmelden(self, q: asyncio.Queue[Umschlag]) -> None:
        self._abos.discard(q)

    def senden(self, u: Umschlag) -> None:
        for q in list(self._abos):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(u)

    @property
    def abonnenten(self) -> int:
        return len(self._abos)
