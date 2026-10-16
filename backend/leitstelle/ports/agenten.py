"""Verbindungen der Knoten-Agenten: wer verbunden ist, was er zuletzt gemeldet hat, Befehle mit Antwort.

Unabhängig vom Transport: der WebSocket-Endpunkt reicht eine Sendefunktion herein und liefert eingehende
Nutzlasten ab. Ein Befehl wartet auf seine Antwort ohne eigene Zeitgrenze; die Grenze für einen Start setzt
der Agent selbst (Startzeit je Dienst). Bricht die Verbindung ab, scheitern offene Befehle sofort.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ..protokoll.knoten import Befehl, BefehlErgebnis, Dienstliste, KnotenAnmeldung, Messwerte
from ..protokoll.umschlag import Umschlag, umschlag

Senden = Callable[[Umschlag], Awaitable[None]]
Beenden = Callable[[], Awaitable[None]]


class AgentGetrennt(Exception):
    """Der Agent des Knotens ist nicht (mehr) verbunden."""


class AgentVerbindung:
    def __init__(self, knoten: str, anmeldung: KnotenAnmeldung, senden: Senden, seit_s: float, beenden: Beenden | None = None) -> None:
        self.knoten = knoten
        self.anmeldung = anmeldung
        self.senden = senden
        self.beenden = beenden          # schließt die Verbindung von der Leitstelle aus (neuer Schlüssel)
        self.seit_s = seit_s
        self.messwerte: Messwerte | None = None
        self.messzeit_s: float | None = None
        self.dienste = Dienstliste()
        self.offen: dict[str, asyncio.Future[BefehlErgebnis]] = {}

    def trennen(self) -> None:
        for f in self.offen.values():
            if not f.done():
                f.set_exception(AgentGetrennt(self.knoten))
        self.offen.clear()


class Agentenvermittlung:
    def __init__(self) -> None:
        self._verbindungen: dict[str, AgentVerbindung] = {}

    def verbindung(self, knoten: str) -> AgentVerbindung | None:
        return self._verbindungen.get(knoten)

    def verbundene(self) -> list[AgentVerbindung]:
        return list(self._verbindungen.values())

    def anmelden(self, knoten: str, anmeldung: KnotenAnmeldung, senden: Senden, jetzt_s: float, beenden: Beenden | None = None) -> AgentVerbindung:
        """Neue Verbindung eines Knotens; eine ältere desselben Knotens gilt als getrennt."""
        alt = self._verbindungen.get(knoten)
        if alt:
            alt.trennen()
        v = AgentVerbindung(knoten, anmeldung, senden, jetzt_s, beenden)
        self._verbindungen[knoten] = v
        return v

    def abmelden(self, v: AgentVerbindung) -> bool:
        """Trennt die Verbindung; True, wenn sie die aktuelle des Knotens war."""
        v.trennen()
        if self._verbindungen.get(v.knoten) is v:
            del self._verbindungen[v.knoten]
            return True
        return False

    async def befehl(self, knoten: str, befehl: Befehl) -> BefehlErgebnis:
        v = self._verbindungen.get(knoten)
        if v is None:
            raise AgentGetrennt(knoten)
        u = umschlag("knoten.befehl", befehl, an=f"agent:{knoten}")
        zukunft: asyncio.Future[BefehlErgebnis] = asyncio.get_running_loop().create_future()
        v.offen[u.id] = zukunft
        try:
            await v.senden(u)
            return await zukunft
        finally:
            v.offen.pop(u.id, None)

    @staticmethod
    def ergebnis(v: AgentVerbindung, bezug: str | None, e: BefehlErgebnis) -> None:
        f = v.offen.get(bezug or "")
        if f and not f.done():
            f.set_result(e)
