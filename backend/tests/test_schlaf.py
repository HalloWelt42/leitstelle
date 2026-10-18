"""Schlaf eines Rechners: die Leitstelle wartet, bis er wach ist (Entwurf "Warten, bis der Mac wach ist", 19.10.2026).

Leitstelle, Schein-Läufer und Schein-Agent auf echten Ports; Rechner, Dienst und Anwendung über die Verwaltung. Der
Läufer liegt auf demselben Rechner wie der Agent, wie LM Studio neben dem Maschinenraum. Szenarien R01 bis R07 aus
docs/SZENARIEN.md.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI

from leitstelle.api.app import erstellen
from leitstelle.kern.modelle import Regelwerk
from leitstelle.kern.werte import Automatik
from leitstelle.konfig import Konfig
from leitstelle.ports.ablage.datenbank import Datenbank
from leitstelle.ports.ablage.repositorien import Ablage
from leitstelle.ports.uhr import Stelluhr, Uhr

from schein.agent import ScheinAgent
from schein.laeufer import Lage, schein_laeufer
from schein.server import laufend

MODELL = "qwen/qwen3-next-80b"
SATZ = "Mac Studio schläft; der Auftrag kann erst laufen, wenn er wach ist."


@dataclass
class Aufbau:
    c: httpx.AsyncClient          # Verwaltung
    anw: httpx.AsyncClient        # Anwendung (Fassade)
    url: str
    knoten: str
    agent: ScheinAgent
    laeufer: Lage
    app: FastAPI


@asynccontextmanager
async def leitstelle(tmp_path, uhr: Uhr | None = None, mit_takt: bool = True):
    app = erstellen(Konfig(daten=tmp_path, oberflaeche=None, dienst_takt_s=0.3, hinweis_s=1.0), uhr=uhr, mit_takt=mit_takt)
    async with laufend(app) as url, httpx.AsyncClient(base_url=url, timeout=30) as c:
        yield app, url, c


@asynccontextmanager
async def aufbau(tmp_path, uhr: Uhr | None = None, mit_takt: bool = True, regelwerk: Regelwerk | None = None):
    """Mac Studio mit Läufer und Maschinenraum (Schein-Agent, verbunden, Dienst Probe gemeldet), eine Anwendung."""
    if regelwerk is not None:
        db = Datenbank(tmp_path / "leitstelle.sqlite")
        await db.oeffnen()
        await Ablage(db).einstellungen.regelwerk_speichern(regelwerk)
        await db.schliessen()
    laeufer = schein_laeufer()
    async with laufend(laeufer) as laeufer_url, leitstelle(tmp_path, uhr, mit_takt) as (app, url, c):
        r = await c.post("/api/dienste", json={"adresse": laeufer_url, "plaetze": 4,
                                                 "neuer_knoten": {"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": 128}})
        assert r.status_code == 200, r.text
        knoten = r.json()["knoten"]
        schluessel = (await c.post(f"/api/knoten/{knoten}/agent/schluessel/neu")).json()["schluessel"]
        r = await c.post("/api/anwendungen", json={"name": "Transkription", "faehigkeiten": ["text", "stimme"]})
        anw = httpx.AsyncClient(base_url=url, timeout=30, headers={"Authorization": f"Bearer {r.json()['schluessel']}"})
        agent = ScheinAgent(url, schluessel)
        await agent.verbinden()
        a = Aufbau(c=c, anw=anw, url=url, knoten=knoten, agent=agent, laeufer=laeufer.state.lage, app=app)
        await _warte_bis(lambda: _modell_da(a, "probe"))
        try:
            yield a
        finally:
            await agent.beenden()
            await anw.aclose()


async def _warte_bis(bedingung, sekunden: float = 10.0):
    for _ in range(int(sekunden * 20)):
        if await bedingung():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Bedingung nicht erreicht")


async def _lage(a: Aufbau) -> dict:
    return (await a.c.get("/api/lage")).json()


async def _modell_da(a: Aufbau, familie: str) -> bool:
    return any(m["familie"] == familie for m in (await _lage(a))["modelle"])


async def _knoten(a: Aufbau) -> dict:
    return next(k for k in (await _lage(a))["knoten"] if k["kennung"] == a.knoten)


async def _dienste(a: Aufbau) -> list[dict]:
    return [d for d in (await _lage(a))["dienste"] if d["knoten"] == a.knoten]


def _schlaf_absage(r: httpx.Response) -> None:
    assert r.status_code == 503, r.text
    f = r.json()["error"]
    assert (f["code"], f["message"], f["x-leitstelle"]) == ("rechner_schlaeft", SATZ, {"rechner": ["Mac Studio"]})
    assert r.headers["retry-after"] == "60"


async def test_r01_schlaf_vermerkt_ohne_pruefung_und_lage_ruhig(tmp_path):
    async with aufbau(tmp_path) as a:
        assert await a.agent.schlafen()
        k = await _knoten(a)
        assert k["zustand"] == "schlaeft" and not k["erreichbar"] and k["schlaeft_seit_s"] is not None
        aufrufe = a.laeufer.aufrufe
        await asyncio.sleep(2.5)                                       # viele Takte zu 0,3 s
        assert a.laeufer.aufrufe == aufrufe, "der Läufer auf dem schlafenden Rechner wird nicht gefragt"
        dienste = await _dienste(a)
        assert len(dienste) == 2 and all(d["zustand"] == "schlaeft" and d["fehlschlaege"] == 0 for d in dienste)
        bild = await _lage(a)
        assert bild["lage"] == "ruhig" and bild["lage_grund"].endswith("Mac Studio schläft")
        texte = [m["text"] for m in bild["meldungen"]]
        assert any(t.startswith("Mac Studio schläft (nach Leerlauf)") for t in texte)
        assert "Maschinenraum auf Mac Studio getrennt: der Rechner schläft" in texte


async def test_r02_anfragen_bekommen_503_mit_dem_rechner(tmp_path):
    async with aufbau(tmp_path) as a:
        await a.agent.schlafen()
        _schlaf_absage(await a.anw.post("/v1/chat/completions", json={"model": MODELL, "messages": []}))
        _schlaf_absage(await a.anw.post("/v1/chat/completions", json={"model": MODELL, "stream": True, "messages": []}))
        _schlaf_absage(await a.anw.get("/v1/dienste/probe/hallo.txt"))
        e = (await a.c.get("/api/auftraege", params={"zustand": "abgelehnt"})).json()["eintraege"]
        assert {x["grund"] for x in e} == {"rechner_schlaeft"}


async def test_r03_laufender_auftrag_endet_auch_ohne_automatik(tmp_path):
    """Automatik "vorschlagen": die Regel Umverteilen bei Ausfall greift nicht, der Schlaf beendet laufende Aufträge
    trotzdem (sie hingen sonst bis zum Aufwachen)."""
    async with aufbau(tmp_path, regelwerk=Regelwerk(automatik=Automatik.VORSCHLAGEN)) as a:
        a.laeufer.stueck_pause_s, a.laeufer.stuecke = 0.3, 30
        ganz = asyncio.create_task(a.anw.post("/v1/chat/completions", json={"model": MODELL, "messages": []}))
        strom = asyncio.create_task(a.anw.post("/v1/chat/completions", json={"model": MODELL, "stream": True, "messages": []}))

        async def laufen_beide():
            return sum(1 for x in (await _lage(a))["auftraege"] if x["zustand"] == "laeuft") == 2
        await _warte_bis(laufen_beide)
        await asyncio.sleep(0.5)
        await a.agent.schlafen()
        _schlaf_absage(await asyncio.wait_for(ganz, 5))
        r = await asyncio.wait_for(strom, 5)
        letztes = [z for z in r.text.splitlines() if z.startswith("data: {")][-1]
        assert '"finish_reason": "leitstelle_abbruch"' in letztes and '"grund": "rechner_schlaeft"' in letztes and '"rechner": ["Mac Studio"]' in letztes

        async def beide_vermerkt():
            e = (await a.c.get("/api/auftraege", params={"zustand": "abgebrochen"})).json()["eintraege"]
            return len(e) == 2 and {x["grund"] for x in e} == {"rechner_schlaeft"}
        await _warte_bis(beide_vermerkt, 3)


async def test_r04_nach_der_nacht_kein_ausfall_und_gleich_bereit(tmp_path):
    """Zwölf Stunden Schlaf mit vielen Takten: der Läufer auf demselben Rechner zählt keinen Fehlschlag, steht nicht im
    Ausfall und ist gleich nach dem Aufwachen bereit (ohne die wachsenden Prüfabstände eines Ausfalls)."""
    uhr = Stelluhr()
    async with aufbau(tmp_path, uhr=uhr, mit_takt=False) as a:
        betrieb = a.app.state.betrieb
        await a.agent.schlafen()
        a.laeufer.aus = True                                           # der Rechner schläft wirklich
        aufrufe = a.laeufer.aufrufe
        for _ in range(12):
            uhr.vor(3600)
            await betrieb.takt()
        assert a.laeufer.aufrufe == aufrufe
        laeufer = next(d for d in await _dienste(a) if d["art"] == "openai_kompatibel")
        assert laeufer["zustand"] == "schlaeft" and laeufer["fehlschlaege"] == 0
        a.laeufer.aus = False
        await a.agent.wecken()

        async def bereit():
            d = next(x for x in await _dienste(a) if x["art"] == "openai_kompatibel")
            return d["zustand"] == "bereit" and (await _knoten(a))["zustand"] == "erreichbar"
        await _warte_bis(bereit, 3)                                    # ohne Takt: sofort beim Aufwachen geprüft
        assert any(m["text"] == "Mac Studio ist aufgewacht nach 12,0 h" for m in (await _lage(a))["meldungen"])
        r = await a.anw.post("/v1/chat/completions", json={"model": MODELL, "messages": []})
        assert r.status_code == 200, r.text


async def test_r05_schlaf_uebersteht_den_neustart(tmp_path):
    laeufer = schein_laeufer()
    async with laufend(laeufer) as laeufer_url:
        async with leitstelle(tmp_path) as (_app, url, c):
            r = await c.post("/api/dienste", json={"adresse": laeufer_url, "neuer_knoten": {"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": 128}})
            knoten = r.json()["knoten"]
            schluessel = (await c.post(f"/api/knoten/{knoten}/agent/schluessel/neu")).json()["schluessel"]
            app_schluessel = (await c.post("/api/anwendungen", json={"name": "Transkription", "faehigkeiten": ["text", "stimme"]})).json()["schluessel"]
            agent = ScheinAgent(url, schluessel)
            await agent.verbinden()
            await agent.schlafen()
        laeufer.state.lage.aus = True
        async with leitstelle(tmp_path) as (app, url, c):
            a = Aufbau(c=c, anw=httpx.AsyncClient(base_url=url, headers={"Authorization": f"Bearer {app_schluessel}"}), url=url, knoten=knoten,
                       agent=ScheinAgent(url, schluessel), laeufer=laeufer.state.lage, app=app)
            try:
                await asyncio.sleep(1.0)
                assert (await _knoten(a))["zustand"] == "schlaeft"
                assert all(d["zustand"] == "schlaeft" and d["fehlschlaege"] == 0 for d in await _dienste(a))
                assert (await _lage(a))["lage"] == "ruhig"
                _schlaf_absage(await a.anw.get("/v1/dienste/probe/hallo.txt"))           # nach dem Neustart unbekannt, liegt aber dort
                _schlaf_absage(await a.anw.post("/v1/chat/completions", json={"model": MODELL, "messages": []}))
                laeufer.state.lage.aus = False
                await a.agent.wecken()

                async def wach():
                    return (await a.anw.post("/v1/chat/completions", json={"model": MODELL, "messages": []})).status_code == 200
                await _warte_bis(wach)
                assert (await _knoten(a))["zustand"] == "erreichbar"
            finally:
                await a.agent.beenden()
                await a.anw.aclose()


async def test_r06_unangekuendigt_weg_gibt_503_statt_403(tmp_path):
    """Vorfall: verschwand der Rechner ohne Abmeldung, lehnte die Leitstelle nach wenigen Sekunden mit 403
    zone_nicht_erlaubt ab, und die Apps gaben auf. Richtig ist 503 dienst_nicht_erreichbar (die App wartet begrenzt)."""
    async with aufbau(tmp_path) as a:
        a.laeufer.aus = True
        await a.agent.trennen()

        async def weg():
            return (await _knoten(a))["zustand"] == "nicht_erreichbar"
        await _warte_bis(weg)
        for r in (await a.anw.get("/v1/dienste/probe/hallo.txt"), await a.anw.post("/v1/chat/completions", json={"model": MODELL, "messages": []})):
            assert r.status_code == 503 and r.json()["error"]["code"] == "dienst_nicht_erreichbar", r.text
            assert "x-leitstelle" not in r.json()["error"] and r.headers["retry-after"] == "30"


async def test_r07_nicht_mehr_warten(tmp_path):
    async with aufbau(tmp_path) as a:
        await a.agent.schlafen()
        a.laeufer.aus = True
        r = await a.c.post(f"/api/knoten/{a.knoten}/schlaf_beenden")
        assert r.status_code == 200, r.text

        async def geprueft():
            return all(d["zustand"] == "nicht_erreichbar" for d in await _dienste(a)) and (await _knoten(a))["zustand"] == "nicht_erreichbar"
        await _warte_bis(geprueft)
        r = await a.anw.post("/v1/chat/completions", json={"model": MODELL, "messages": []})
        assert r.status_code == 503 and r.json()["error"]["code"] == "dienst_nicht_erreichbar"
        pruef = [e["was"] for e in (await a.c.get("/api/pruefprotokoll")).json()["eintraege"]]
        assert "Schlafzustand von Hand beendet" in pruef
        r = await a.c.post(f"/api/knoten/{a.knoten}/schlaf_beenden")
        assert r.status_code == 404 and r.json()["grund"] == "unbekannt"
