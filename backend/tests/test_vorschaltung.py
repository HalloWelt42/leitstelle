"""HTTPS über den Vorschaltdienst: Herkunft aus X-Forwarded-For nur vom eingestellten Vorschaltdienst."""

from __future__ import annotations

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from leitstelle.__main__ import serveroptionen
from leitstelle.konfig import Konfig

VORNE = "10.201.53.2"


def _herkunft(request: Request) -> PlainTextResponse:
    return PlainTextResponse(request.client.host if request.client else "")


def _wie_im_betrieb(konfig: Konfig):
    """Die App so verpackt, wie uvicorn sie mit den Serveroptionen der Konfig startet."""
    app = Starlette(routes=[Route("/", _herkunft)])
    optionen = serveroptionen(konfig)
    if not optionen["proxy_headers"]:
        return app
    return ProxyHeadersMiddleware(app, trusted_hosts=optionen["forwarded_allow_ips"])


async def _abfragen(app, absender: str, kopf: dict[str, str]) -> str:
    transport = httpx.ASGITransport(app=app, client=(absender, 40000))
    async with httpx.AsyncClient(transport=transport, base_url="http://kern") as c:
        return (await c.get("/", headers=kopf)).text


def test_ohne_vorschaltung_zaehlt_der_kopf_nie():
    assert serveroptionen(Konfig())["proxy_headers"] is False


async def test_vom_vorschaltdienst_gilt_der_echte_aufrufer():
    app = _wie_im_betrieb(Konfig(vorschaltung=[VORNE]))
    assert await _abfragen(app, VORNE, {"X-Forwarded-For": "192.168.178.45"}) == "192.168.178.45"


async def test_anderer_absender_kann_seine_herkunft_nicht_behaupten():
    app = _wie_im_betrieb(Konfig(vorschaltung=[VORNE]))
    assert await _abfragen(app, "203.0.113.9", {"X-Forwarded-For": "192.168.178.45"}) == "203.0.113.9"
    assert not Konfig(vorschaltung=[VORNE]).erlaubt("203.0.113.9")
