"""Ein Aufruf eines Dienstes (`/v1/dienste/<name>/<pfad>`), dessen Anwendung mittendrin geht, hinterlässt keinen offenen
Auftrag. Befund vom 28.11.2026: ging eine Anwendung, während sie den Körper noch schickte, stand der Auftrag schon und blieb
für immer "läuft"; der Dienst (Klonstimmen) war belegt, und alle folgenden Aufträge warteten dahinter."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from leitstelle.api import fassade
from leitstelle.kern.werte import Faehigkeit, Prioritaet


class Vermittlung:
    """Merkt, was mit Aufträgen geschieht; die Durchleitung scheitert so, wie der Test es will."""

    def __init__(self, scheitern: BaseException | None = None) -> None:
        self.angenommen: list[SimpleNamespace] = []
        self.aufgeraeumt: list[SimpleNamespace] = []
        self._scheitern = scheitern

    def faehigkeit_fuer(self, anwendung: str, familie: str) -> Faehigkeit:
        return Faehigkeit.STIMME_KLONEN

    def annehmen(self, *_: object, **__: object) -> SimpleNamespace:
        v = SimpleNamespace(lauf=SimpleNamespace(beenden_mit=lambda *_: None))
        self.angenommen.append(v)
        return v

    async def warten(self, v: SimpleNamespace):
        return
        yield

    async def roh_anfragen(self, v: SimpleNamespace, anfrage: object) -> object:
        assert self._scheitern is not None
        raise self._scheitern

    def aufraeumen(self, v: SimpleNamespace) -> None:
        self.aufgeraeumt.append(v)


def _anfrage(verm: Vermittlung, teile: list[dict]) -> Request:
    """Eine Anfrage, deren Körper in diesen Teilen ankommt; danach hört die Verbindung nichts mehr."""
    betrieb = SimpleNamespace(
        familie_fuer=lambda name: name,
        anwendung_zum_schluessel=lambda s: SimpleNamespace(kennung="vertonung", prioritaet=Prioritaet.NORMAL) if s == "geheim" else None,
        verbund=SimpleNamespace(modelle={}, knoten={}),
    )
    app = SimpleNamespace(state=SimpleNamespace(betrieb=betrieb, vermittlung=verm, konfig=SimpleNamespace(wieder_s=5, schlaf_wieder_s=60)))
    reihe = list(teile)

    async def empfangen() -> dict:
        if reihe:
            return reihe.pop(0)
        await asyncio.Event().wait()            # still: die Wache der Fassade wartet hier, bis sie endet
        return {"type": "http.disconnect"}

    scope = {"type": "http", "method": "POST", "path": "/v1/dienste/klangwerk-klonen/tts/clone", "query_string": b"",
             "headers": [(b"authorization", b"Bearer geheim")], "app": app}
    return Request(scope, empfangen)


async def test_geht_die_anwendung_beim_senden_entsteht_kein_auftrag():
    verm = Vermittlung()
    anfrage = _anfrage(verm, [{"type": "http.request", "body": b"text=Ein Satz", "more_body": True}, {"type": "http.disconnect"}])
    antwort = await fassade.dienst(anfrage, "klangwerk-klonen", "tts/clone")
    assert antwort.status_code == 400
    assert verm.angenommen == []


@pytest.mark.parametrize("abbruch", [RuntimeError("Dienst kaputt"), asyncio.CancelledError()])
async def test_jeder_andere_abbruch_schliesst_den_auftrag(abbruch):
    verm = Vermittlung(scheitern=abbruch)
    anfrage = _anfrage(verm, [{"type": "http.request", "body": b"text=Ein Satz", "more_body": False}])
    with pytest.raises(type(abbruch)):
        await fassade.dienst(anfrage, "klangwerk-klonen", "tts/clone")
    assert len(verm.angenommen) == 1 and verm.aufgeraeumt == verm.angenommen
