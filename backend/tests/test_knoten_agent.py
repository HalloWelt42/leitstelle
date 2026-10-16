"""Knoten-Agent Ende zu Ende: echte Leitstelle auf einem Port, echter Agent (Paket `leitstelle_agent`) mit einem
kleinen HTTP-Server als Prozessdienst. Szenarien A01 bis A06 aus docs/SZENARIEN.md."""

from __future__ import annotations

import asyncio
import contextlib
import io
import socket
import sys
import tarfile
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
import websockets

from leitstelle.api.app import erstellen
from leitstelle.konfig import Konfig

from schein.server import laufend

agent = pytest.importorskip("leitstelle_agent")
from leitstelle_agent.kanal import Kanal  # noqa: E402
from leitstelle_agent.konfig import Agentenordner  # noqa: E402
from leitstelle_agent.messen import Messer  # noqa: E402
from leitstelle_agent.prozesse import Verwalter  # noqa: E402

WURZEL = Path(__file__).resolve().parents[2]


def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _offen(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


async def _warte_bis(bedingung, sekunden: float = 15.0):
    for _ in range(int(sekunden * 10)):
        if await bedingung():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("Bedingung nicht erreicht")


def _agentenordner(tmp: Path, url: str, schluessel: str, port: int) -> Agentenordner:
    o = tmp / "agent"
    (o / "dienste").mkdir(parents=True)
    (o / "agent.toml").write_text(f'leitstelle = "{url}"\ntakt_s = 1\nmacmon = false\nwiederverbindung_max_s = 1\n')
    (o / "schluessel").write_text(schluessel)
    (o / "dienste" / "probe.toml").write_text(
        f'name = "Probe"\nordner = "{tmp}"\nbefehl = ["{sys.executable}", "-m", "http.server", "{port}", "--bind", "127.0.0.1"]\n'
        f'port = {port}\nfaehigkeiten = ["stimme"]\nspeicher_gb = 0.5\nstartzeit_s = 15\nanhaltezeit_s = 5\n')
    return Agentenordner(o)


@asynccontextmanager
async def aufbau(tmp_path: Path):
    """Leitstelle mit einem Rechner (64 GB eingetragen, 6 GB System geschätzt) und einem Agent-Schlüssel."""
    app = erstellen(Konfig(daten=tmp_path / "daten", oberflaeche=None, dienst_takt_s=0.3, agent_quelle=WURZEL / "agent"))
    async with laufend(app) as url, httpx.AsyncClient(base_url=url, timeout=30) as c:
        r = await c.post("/api/knoten", json={"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": 64, "system_gb": 6})
        assert r.status_code == 200, r.text
        knoten = r.json()["kennung"]
        assert r.json()["agent_schluessel"] is False
        schluessel = (await c.post(f"/api/knoten/{knoten}/agent/schluessel/neu")).json()["schluessel"]
        r = await c.put(f"/api/knoten/{knoten}", json={"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": 64, "system_gb": 6})
        assert r.json()["agent_schluessel"] is True and "agent_geheim" not in r.json()     # Ändern behält den Schlüssel, zeigt ihn nie
        yield c, url, knoten, schluessel


@asynccontextmanager
async def agent_laeuft(o: Agentenordner):
    konfig = o.konfig()
    verwalter = Verwalter(o, konfig)
    messer = Messer(konfig.takt_s, macmon=False)
    aufgaben = [asyncio.create_task(verwalter.schleife()), asyncio.create_task(Kanal(o, konfig, verwalter, messer).schleife())]
    try:
        yield verwalter
    finally:
        for t in aufgaben:
            t.cancel()
        await asyncio.gather(*aufgaben, return_exceptions=True)
        for d in verwalter.dienste.values():
            if d.stand.gruppe is not None:
                await d.anhalten()


async def _knoten(c: httpx.AsyncClient, kennung: str) -> dict:
    return next(k for k in (await c.get("/api/lage")).json()["knoten"] if k["kennung"] == kennung)


async def _modell(c: httpx.AsyncClient, familie: str) -> dict | None:
    return next((m for m in (await c.get("/api/lage")).json()["modelle"] if m["familie"] == familie), None)


async def test_a01_agent_meldet_echten_speicher(tmp_path):
    async with aufbau(tmp_path) as (c, url, knoten, schluessel):
        o = _agentenordner(tmp_path, url, schluessel, _freier_port())
        async with agent_laeuft(o):
            async def gemessen():
                return (await _knoten(c, knoten))["agent"]["messwerte"] is not None
            await _warte_bis(gemessen)
            k = await _knoten(c, knoten)
            mw = k["agent"]["messwerte"]
            assert k["agent"]["verbunden"] and k["agent"]["schluessel"] and k["agent"]["version"]
            assert k["speicher_gb"] == pytest.approx(mw["speicher_gesamt_gb"], abs=0.01)       # gemessen statt eingetragen
            assert k["system_gb"] == pytest.approx(max(0.0, mw["speicher_belegt_gb"] - k["geladen_gb"]), abs=0.05)
            assert k["belegt_anteil"] == pytest.approx(min(1.0, mw["speicher_belegt_gb"] / mw["speicher_gesamt_gb"]), abs=0.02)


async def test_a02_falscher_schluessel_wird_abgewiesen(tmp_path):
    async with aufbau(tmp_path) as (_c, url, _knoten, _schluessel):
        with pytest.raises(websockets.exceptions.ConnectionClosed) as f:
            async with websockets.connect(url.replace("http", "ws") + "/agent/kanal", additional_headers={"Authorization": "Bearer ls_falsch"}) as ws:
                await ws.recv()
        assert f.value.rcvd.code == 4401


async def test_a03_dienst_starten_und_anhalten_ueber_die_leitstelle(tmp_path):
    port = _freier_port()
    async with aufbau(tmp_path) as (c, url, knoten, schluessel):
        async with agent_laeuft(_agentenordner(tmp_path, url, schluessel, port)):
            async def da():
                return await _modell(c, "probe") is not None
            await _warte_bis(da)
            m = await _modell(c, "probe")
            assert m["zustand"] == "frei" and m["geschuetzt"] and m["faehigkeiten"] == ["stimme"] and m["knoten"] == knoten
            dienst = next(d for d in (await c.get("/api/lage")).json()["dienste"] if d["kennung"] == m["dienst"])
            assert dienst["art"] == "agent" and dienst["name"] == "Dienste auf Mac Studio" and dienst["steuerbar"]

            assert (await c.post(f"/api/modelle/{m['kennung']}/laden")).status_code == 200

            async def geladen():
                return (await _modell(c, "probe"))["zustand"] == "geladen"
            await _warte_bis(geladen)
            assert _offen(port)

            assert (await c.post(f"/api/modelle/{m['kennung']}/entladen")).status_code == 200

            async def aus():
                return not _offen(port)
            await _warte_bis(aus)
            await asyncio.sleep(1.5)
            assert (await _modell(c, "probe"))["zustand"] == "frei"
            pruef = [e["was"] for e in (await c.get("/api/pruefprotokoll")).json()["eintraege"]]
            assert "Modell von Hand geladen" in pruef and "Modell von Hand entladen" in pruef


async def test_a04_ohne_agent_gelten_die_eingetragenen_werte(tmp_path):
    async with aufbau(tmp_path) as (c, url, knoten, schluessel):
        async with agent_laeuft(_agentenordner(tmp_path, url, schluessel, _freier_port())):
            async def verbunden():
                k = await _knoten(c, knoten)
                return k["agent"]["messwerte"] is not None and await _modell(c, "probe") is not None
            await _warte_bis(verbunden)

        async def getrennt():
            return not (await _knoten(c, knoten))["agent"]["verbunden"]
        await _warte_bis(getrennt)
        k = await _knoten(c, knoten)
        assert k["speicher_gb"] == 64 and k["system_gb"] == 6
        dienst = next(d for d in (await c.get("/api/lage")).json()["dienste"] if d["art"] == "agent")

        async def unerreichbar():
            d = next(x for x in (await c.get("/api/lage")).json()["dienste"] if x["kennung"] == dienst["kennung"])
            return d["zustand"] == "nicht_erreichbar"
        await _warte_bis(unerreichbar)


async def test_a05_neuer_schluessel_trennt_den_agenten(tmp_path):
    async with aufbau(tmp_path) as (c, url, knoten, schluessel):
        async with agent_laeuft(_agentenordner(tmp_path, url, schluessel, _freier_port())):
            async def verbunden():
                return (await _knoten(c, knoten))["agent"]["verbunden"]
            await _warte_bis(verbunden)
            neu = (await c.post(f"/api/knoten/{knoten}/agent/schluessel/neu")).json()["schluessel"]
            assert neu != schluessel

            async def getrennt():
                return not (await _knoten(c, knoten))["agent"]["verbunden"]
            await _warte_bis(getrennt)
            await asyncio.sleep(2.5)                      # Agent versucht es erneut, mit dem alten Schlüssel vergeblich
            assert not (await _knoten(c, knoten))["agent"]["verbunden"]
            assert (await c.post(f"/api/knoten/{knoten}/agent/schluessel")).json()["schluessel"] == neu
            pruef = [e["was"] for e in (await c.get("/api/pruefprotokoll")).json()["eintraege"]]
            assert "Agent-Schlüssel neu erzeugt" in pruef and "Agent-Schlüssel aufgedeckt" in pruef


async def test_a06_installationsskript_und_paket(tmp_path):
    async with aufbau(tmp_path) as (c, url, _knoten, _schluessel):
        r = await c.get("/agent/installieren.sh")
        assert r.status_code == 200 and f'LEITSTELLE="${{LEITSTELLE:-{url}}}"' in r.text and "__LEITSTELLE_ADRESSE__" not in r.text
        r = await c.get("/agent/paket.tar.gz")
        assert r.status_code == 200
        with tarfile.open(fileobj=io.BytesIO(r.content)) as tar:
            namen = tar.getnames()
            assert "leitstelle-agent/pyproject.toml" in namen and "leitstelle-agent/leitstelle_agent/prozesse.py" in namen
            assert not any("/tests/" in n or "__pycache__" in n or ".egg-info" in n for n in namen)
            fassung = tar.extractfile("leitstelle-agent/leitstelle_agent/VERSION").read().decode()
        assert fassung == (await c.get("/gesundheit")).json()["version"]


def test_protokoll_von_agent_und_kern_ist_deckungsgleich():
    import leitstelle.protokoll.knoten as kern
    import leitstelle_agent.protokoll as spiegel
    for name in ("KnotenAnmeldung", "Messwerte", "Prozesszustand", "ProzessBericht", "Dienstliste", "Befehlsart", "Befehl", "BefehlErgebnis", "Faehigkeit"):
        a, b = getattr(kern, name, None) or getattr(__import__("leitstelle.kern.werte", fromlist=[name]), name), getattr(spiegel, name)
        if hasattr(a, "model_json_schema"):
            assert a.model_json_schema() == b.model_json_schema(), name
        else:
            assert [e.value for e in a] == [e.value for e in b], name
