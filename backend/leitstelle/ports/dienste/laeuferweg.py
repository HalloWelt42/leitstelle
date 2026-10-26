"""Weg zum Modell-Läufer über den Maschinenraum seines Rechners (PROTOKOLL 4.2, Durchleitung `/laeufer/<pfad>`).

Ein httpx-Transport unter dem Adapter des Läufers: jede Anfrage geht statt an die eingetragene Adresse an die
Durchleitung des Maschinenraums, mit dessen Schlüssel als Bearer. Adresse und Schlüssel kommen bei jeder Anfrage aus der
Agentenverbindung; es gibt keinen zweiten Schlüssel und keine feste Adresse. So kommt jede Verbindung der Leitstelle zum
Läufer vom Maschinenraum selbst, und jede andere ist für seine Beobachtung eine Umgehung.

Ist der Maschinenraum nicht verbunden, scheitert die Anfrage mit `OhneMaschinenraum`; einen stillen Rückfall auf den
direkten Weg gibt es nicht (Umgehungen wären sonst wieder unsichtbar). Der Rückfall ist der Schalter von Hand: aus heißt
sofort wieder direkt, die eingetragene Adresse bleibt dafür unverändert stehen.
"""

from __future__ import annotations

import httpx

from ...protokoll.knoten import DURCHLEITUNG_LAEUFER
from ..agenten import Agentenvermittlung

OHNE_MASCHINENRAUM = "Maschinenraum nicht verbunden; Rückfall: Schalter 'über den Maschinenraum' aus"
OHNE_KOPF = frozenset({"host", "authorization"})     # setzt der Weg selbst (Ziel und Schlüssel des Maschinenraums)


class OhneMaschinenraum(httpx.ConnectError):
    """Der Weg über den Maschinenraum ist zu: kein Agent verbunden, oder er meldet keine Durchleitung."""


class UeberMaschinenraum(httpx.AsyncBaseTransport):
    def __init__(self, knoten: str, agenten: Agentenvermittlung, innen: httpx.AsyncBaseTransport | None = None) -> None:
        self.knoten = knoten
        self.agenten = agenten
        self._innen = innen or httpx.AsyncHTTPTransport()

    def umlenken(self, anfrage: httpx.Request) -> httpx.Request:
        """Dieselbe Anfrage an `/laeufer<pfad>` der Durchleitung, mit dem Schlüssel des Maschinenraums."""
        v = self.agenten.verbindung(self.knoten)
        basis = v.durchleitung if v else None
        if v is None or basis is None:
            raise OhneMaschinenraum(OHNE_MASCHINENRAUM, request=anfrage)
        ziel = basis.copy_with(raw_path=f"/{DURCHLEITUNG_LAEUFER}".encode() + anfrage.url.raw_path)
        kopf = [("host", ziel.netloc.decode("ascii"))]       # mit fertigem Strom setzt httpx den Kopf nicht selbst
        kopf += [(k, w) for k, w in anfrage.headers.multi_items() if k.lower() not in OHNE_KOPF]
        kopf.append(("authorization", f"Bearer {v.schluessel}"))
        return httpx.Request(anfrage.method, ziel, headers=kopf, stream=anfrage.stream, extensions=anfrage.extensions)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self._innen.handle_async_request(self.umlenken(request))

    async def aclose(self) -> None:
        await self._innen.aclose()
