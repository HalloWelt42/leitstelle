"""Der Modell-Läufer eines Rechners über die Durchleitung seines Maschinenraums (HELF-166, Entscheidung des Nutzers: ein
Weg je Rechner). Ein Läufer-Dienst hat die Adresse `laeufer://<knoten>`; der Adapter bleibt der übliche
(`OpenAIKompatibel`), nur sein Transport reicht jede Anfrage über die Durchleitung des Knotens unter `/_laeufer/`, mit dem
Schlüssel des Maschinenraums und, wenn er es meldet, über TLS. Ist der Maschinenraum nicht verbunden, scheitert die
Verbindung wie bei einem Läufer, der nicht antwortet."""

from __future__ import annotations

import ssl
from pathlib import Path

import httpx

from ..agenten import Agentenvermittlung

SCHEMA = "laeufer://"
#: Ziel des Läufers in der Durchleitung des Maschinenraums (dort ein reservierter Name neben den Diensten)
ZIEL = "_laeufer"
#: Basis für den Adapter; der Transport ersetzt sie durch die Durchleitung des Knotens
BASIS = "http://laeufer"


def laeufer_adresse(knoten: str) -> str:
    return f"{SCHEMA}{knoten}"


def ist_laeufer(adresse: str) -> bool:
    return adresse.startswith(SCHEMA)


def knoten_von(adresse: str) -> str:
    return adresse[len(SCHEMA):].strip("/")


def tls_kontext(ca_datei: Path | None) -> ssl.SSLContext:
    """Die üblichen Stellen und, wenn eingetragen, die Hausstelle."""
    kontext = ssl.create_default_context()
    if ca_datei is not None and Path(ca_datei).is_file():
        kontext.load_verify_locations(cafile=str(ca_datei))
    return kontext


class DurchleitungTransport(httpx.AsyncBaseTransport):
    """Schreibt jede Anfrage auf die Durchleitung des Knotens um (`<durchleitung>/_laeufer/<pfad>`) und setzt den
    Schlüssel des Maschinenraums; Körper und Antwort gehen als Strom unverändert hindurch."""

    def __init__(self, agenten: Agentenvermittlung, knoten: str, innen: httpx.AsyncBaseTransport | None = None,
                 tls: ssl.SSLContext | None = None) -> None:
        self.agenten, self.knoten = agenten, knoten
        self._innen = innen or httpx.AsyncHTTPTransport(verify=tls or tls_kontext(None))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        v = self.agenten.verbindung(self.knoten)
        basis = v.durchleitung if v else None
        if v is None or basis is None:
            raise httpx.ConnectError("Maschinenraum nicht verbunden oder ohne Durchleitung", request=request)
        ziel = httpx.URL(f"{str(basis).rstrip('/')}/{ZIEL}{request.url.raw_path.decode('ascii')}")
        kopf = [(k, w) for k, w in request.headers.multi_items() if k.lower() not in ("host", "authorization")]
        kopf += [("host", ziel.netloc.decode("ascii")), ("authorization", f"Bearer {v.schluessel}")]
        weiter = httpx.Request(request.method, ziel, headers=kopf, stream=request.stream, extensions=request.extensions)
        return await self._innen.handle_async_request(weiter)

    async def aclose(self) -> None:
        await self._innen.aclose()
