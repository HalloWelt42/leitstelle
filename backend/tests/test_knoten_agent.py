"""Knoten-Agent Ende zu Ende: echte Leitstelle auf einem Port, als Agent der Maschinenraum (eigenes Repo,
Paket `maschinenraum`) mit einem kleinen HTTP-Server als Prozessdienst. Szenarien A01 bis A12 aus docs/SZENARIEN.md."""

from __future__ import annotations

import asyncio
import socket
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace
from pathlib import Path

import httpx
import pytest
import websockets

from leitstelle.api.app import erstellen
from leitstelle.konfig import Konfig

from schein.server import laufend

pytest.importorskip("maschinenraum")
from maschinenraum import durchleitung  # noqa: E402
from maschinenraum.konfig import Ordner  # noqa: E402
from maschinenraum.leitstelle import Leitstellenkanal  # noqa: E402
from maschinenraum.protokoll import Messwerte  # noqa: E402
from maschinenraum.prozesse import Verwalter  # noqa: E402


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


def _agentenordner(tmp: Path, url: str, schluessel: str, port: int, mehr: str = "") -> Ordner:
    """Ordner eines Maschinenraums mit dem Dienst Probe. Die Beobachtung am Leitstand vorbei bleibt aus: sie liest die
    Prozesse und Verbindungen des Rechners, auf dem der Test läuft (lsof, je Takt Sekunden), und hielte damit die
    Dienstmeldungen auf. Einen Modell-Läufer hat er nicht (der echte des Rechners bleibt unberührt)."""
    o = tmp / "maschinenraum"
    (o / "dienste").mkdir(parents=True)
    (o / "einstellungen.toml").write_text(f'[leitstelle]\nadresse = "{url}"\nwiederverbindung_max_s = 1\n[messung]\ntakt_s = 1\nmacmon = false\n'
                                          f'[beobachtung]\naktiv = false\n[nachbar]\nmodell_laeufer = ""\n')
    (o / "schluessel").write_text(schluessel)
    (o / "dienste" / "probe.toml").write_text(
        f'name = "Probe"\nordner = "{tmp}"\nbefehl = ["{sys.executable}", "-m", "http.server", "{port}", "--bind", "127.0.0.1"]\n'
        f'port = {port}\nfaehigkeiten = ["stimme"]\nspeicher_gb = 0.5\nstartzeit_s = 15\nanhaltezeit_s = 5\n{mehr}')
    return Ordner(o)


@asynccontextmanager
async def aufbau(tmp_path: Path):
    """Leitstelle mit einem Rechner (64 GB eingetragen, 6 GB System geschätzt) und einem Agent-Schlüssel."""
    app = erstellen(Konfig(daten=tmp_path / "daten", oberflaeche=None, dienst_takt_s=0.3))
    async with laufend(app) as url, httpx.AsyncClient(base_url=url, timeout=30) as c:
        r = await c.post("/api/knoten", json={"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": 64, "system_gb": 6})
        assert r.status_code == 200, r.text
        knoten = r.json()["kennung"]
        assert r.json()["agent_schluessel"] is False
        schluessel = (await c.post(f"/api/knoten/{knoten}/agent/schluessel/neu")).json()["schluessel"]
        r = await c.put(f"/api/knoten/{knoten}", json={"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": 64, "system_gb": 6})
        assert r.json()["agent_schluessel"] is True and "agent_geheim" not in r.json()     # Ändern behält den Schlüssel, zeigt ihn nie
        yield c, url, knoten, schluessel


class ScheinMesser:
    """Feste Messwerte: die Tests dürfen nicht vom Speicher des Rechners abhängen, auf dem sie laufen
    (ein Rechner mit 15 GB hätte nach der Reserve von 18 GB kein Budget, und jeder Start würde warten)."""

    def messwege(self) -> list[str]:
        return ["speicher", "swap"]

    def messen(self) -> Messwerte:
        return Messwerte(speicher_gesamt_gb=64.0, speicher_belegt_gb=20.0, swap_belegt_gb=0.0, swap_gesamt_gb=2.0)

    def beenden(self) -> None:
        pass


@asynccontextmanager
async def agent_laeuft(o: Ordner):
    """Maschinenraum wie im Betrieb: Dienstverwaltung, Kanal zur Leitstelle und Durchleitung auf einem freien Port.
    Liefert den Kanal (für Schlaf und Aufwachen)."""
    e = o.einstellungen()
    verwalter = Verwalter(o, e)
    messer = ScheinMesser()
    weg = durchleitung.erstellen(SimpleNamespace(ordner=o, verwalter=verwalter, durchleitungen=0))
    async with laufend(weg) as weg_url:
        e.durchleitung.port = int(weg_url.rsplit(":", 1)[1])
        o.einstellungen_speichern(e)
        kanal = Leitstellenkanal(o, verwalter, messer)
        aufgabe = asyncio.create_task(verwalter.schleife())
        kanal.starten()
        try:
            yield kanal
        finally:
            await kanal.beenden()
            await _aufraeumen(verwalter, aufgabe)


async def _aufraeumen(verwalter: Verwalter, aufgabe: asyncio.Task) -> None:
    aufgabe.cancel()
    await asyncio.gather(aufgabe, return_exceptions=True)
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
            assert m["zustand"] == "frei" and not m["geschuetzt"] and m["faehigkeiten"] == ["stimme"] and m["knoten"] == knoten
            assert m["gb"] == 0.5 and m["gb_jetzt"] is None                      # Bedarf aus der Schätzung, noch nichts belegt
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
            assert "Schlüssel für den Maschinenraum neu erzeugt" in pruef and "Schlüssel für den Maschinenraum aufgedeckt" in pruef


async def test_a06_geplant_wird_mit_dem_bedarf_das_system_aus_dem_ist_wert(tmp_path):
    """Der Dienst belegt nach dem Start wenig, braucht laut Schätzung aber 6 GB: die Leitstelle verplant 6 GB,
    rechnet dem System aber nur zu, was die Modelle nicht wirklich belegen."""
    port = _freier_port()
    async with aufbau(tmp_path) as (c, url, knoten, schluessel):
        o = _agentenordner(tmp_path, url, schluessel, port)
        datei = o.dienste_ordner / "probe.toml"
        datei.write_text(datei.read_text().replace("speicher_gb = 0.5", "speicher_gb = 6"))
        async with agent_laeuft(o):
            async def da():
                return await _modell(c, "probe") is not None
            await _warte_bis(da)
            m = await _modell(c, "probe")
            assert (await c.post(f"/api/modelle/{m['kennung']}/laden")).status_code == 200

            async def gemessen():
                x = await _modell(c, "probe")
                return x["zustand"] == "geladen" and x["gb_jetzt"] is not None
            await _warte_bis(gemessen)
            m = await _modell(c, "probe")
            assert m["gb"] == 6 and 0 < m["gb_jetzt"] < 1                        # Bedarf verplant, Ist-Wert gemessen

            async def verrechnet():
                k = await _knoten(c, knoten)
                mw = k["agent"]["messwerte"]
                x = await _modell(c, "probe")
                return mw and abs(k["system_gb"] - max(0.0, mw["speicher_belegt_gb"] - (x["gb_jetzt"] or 0))) < 0.1
            await _warte_bis(verrechnet)
            k = await _knoten(c, knoten)
            assert k["geladen_gb"] == 6                                          # im Budget stehen die 6 GB


async def test_a07_anhalten_nur_von_hand(tmp_path):
    port = _freier_port()
    async with aufbau(tmp_path) as (c, url, knoten, schluessel):
        async with agent_laeuft(_agentenordner(tmp_path, url, schluessel, port, mehr="leitstelle_anhalten = false\n")):
            async def da():
                return await _modell(c, "probe") is not None
            await _warte_bis(da)
            m = await _modell(c, "probe")
            assert m["geschuetzt"]                                                # die Selbststeuerung lässt ihn in Ruhe
            assert (await c.post(f"/api/modelle/{m['kennung']}/laden")).status_code == 200

            async def geladen():
                return (await _modell(c, "probe"))["zustand"] == "geladen"
            await _warte_bis(geladen)
            plan = (await c.post(f"/api/knoten/{knoten}/speicher_freigeben", json={"vorschau": True})).json()["plan"]
            assert [f["darf"] for f in plan if f["modell"] == m["kennung"]] == [False]
            await c.post(f"/api/modelle/{m['kennung']}/entladen")                # die Leitstelle versucht es von Hand
            await asyncio.sleep(2.5)
            assert _offen(port)                                                   # der Maschinenraum lehnt ab
            assert (await _modell(c, "probe"))["zustand"] == "geladen"


async def test_a08_anfrage_an_einen_dienst_nur_ueber_die_leitstelle(tmp_path):
    """Die Anwendung kennt nur die Leitstelle. Der Dienst ist aus und lauscht nur auf seinem Rechner: die Leitstelle
    startet ihn über den Maschinenraum und reicht Anfrage und Antwort durch; der Auftrag steht im Verlauf."""
    port = _freier_port()
    (tmp_path / "hallo.txt").write_text("Grüße aus dem Dienst")
    async with aufbau(tmp_path) as (c, url, knoten, schluessel):
        r = await c.post("/api/anwendungen", json={"name": "Sprache", "faehigkeiten": ["stimme"]})
        app_schluessel = r.json()["schluessel"]
        r = await c.post("/api/anwendungen", json={"name": "Nur Text", "faehigkeiten": ["text"]})
        fremd_schluessel = r.json()["schluessel"]
        async with agent_laeuft(_agentenordner(tmp_path, url, schluessel, port)):
            async def da():
                return await _modell(c, "probe") is not None
            await _warte_bis(da)
            assert (await _modell(c, "probe"))["zustand"] == "frei" and not _offen(port)

            async with httpx.AsyncClient(base_url=url, timeout=60) as anw:
                r = await anw.get("/v1/dienste/probe/hallo.txt", headers={"Authorization": f"Bearer {app_schluessel}"})
                assert r.status_code == 200, r.text
                assert r.content.decode() == "Grüße aus dem Dienst" and r.headers["x-leitstelle-modell"] == "Probe"
                auftrag = r.headers["x-leitstelle-auftrag"]
                instanz = r.headers["x-leitstelle-instanz"]                           # für Folgeaufrufe an dieselbe Instanz
                r = await anw.get("/v1/dienste/probe/hallo.txt", headers={"Authorization": f"Bearer {app_schluessel}", "X-Leitstelle-Instanz": instanz})
                assert r.status_code == 200 and r.headers["x-leitstelle-instanz"] == instanz
                r = await anw.get("/v1/dienste/probe/hallo.txt", headers={"Authorization": f"Bearer {app_schluessel}", "X-Leitstelle-Instanz": "gibt-es-nicht"})
                assert r.status_code == 409 and r.json()["error"]["code"] == "instanz_weg"
                assert _offen(port)                                                   # die Leitstelle hat ihn gestartet

                r = await anw.get("/v1/dienste/probe/fehlt.txt", headers={"Authorization": f"Bearer {app_schluessel}"})
                assert r.status_code == 404                                          # Antwort des Dienstes, unverändert

                r = await anw.get("/v1/dienste/probe/hallo.txt", headers={"Authorization": f"Bearer {fremd_schluessel}"})
                assert r.status_code >= 400 and r.json()["error"]["code"] == "faehigkeit_nicht_erlaubt"
                r = await anw.get("/v1/dienste/gibtsnicht/x", headers={"Authorization": f"Bearer {app_schluessel}"})
                assert r.json()["error"]["code"] == "kein_modell"
                assert (await anw.get("/v1/dienste/probe/hallo.txt")).status_code == 401

            async def fertig():
                return (await c.get(f"/api/auftraege/{auftrag}")).json().get("zustand") == "fertig"
            await _warte_bis(fertig)
            e = (await c.get(f"/api/auftraege/{auftrag}")).json()
            assert e["faehigkeit"] == "stimme" and e["erstes_stueck_s"] is not None


def test_protokoll_von_agent_und_kern_ist_deckungsgleich():
    import leitstelle.protokoll.knoten as kern
    import maschinenraum.protokoll as spiegel
    for name in ("KnotenAnmeldung", "Messwerte", "Prozesszustand", "Selbstauskunft", "ProzessBericht", "Dienstliste", "Befehlsart", "Befehl",
                 "BefehlErgebnis", "Faehigkeit", "Eignung", "Schlafgrund", "KnotenSchlaeft", "Fremdart", "Fremdzugriff", "Fremdzugriffe",
                 "Laeuferrolle", "Laeuferprozess", "DockerContainer", "DockerLast", "AppTeil", "AppsLast", "KnotenLast"):
        a, b = getattr(kern, name, None) or getattr(__import__("leitstelle.kern.werte", fromlist=[name]), name), getattr(spiegel, name)
        if hasattr(a, "model_json_schema"):
            assert a.model_json_schema() == b.model_json_schema(), name
        else:
            assert [e.value for e in a] == [e.value for e in b], name


async def test_a09_nach_dem_neustart_ist_ein_ungemeldeter_dienst_nur_gerade_weg(tmp_path):
    """Vorfall vom 18.10.2026: Nach dem Neustart der Leitstelle kannte sie die Dienste des Mac erst, als sich sein
    Maschinenraum wieder meldete; dazwischen hieß es "kein_modell" (endgültig) und ein echter Auftrag gab auf. Solange ein
    eingetragener Maschinenraum sich nicht gemeldet hat, ist ein unbekannter Name nur vorübergehend nicht erreichbar."""
    port = _freier_port()
    (tmp_path / "hallo.txt").write_text("Grüße aus dem Dienst")
    async with aufbau(tmp_path) as (c, url, knoten, schluessel):
        app_schluessel = (await c.post("/api/anwendungen", json={"name": "Sprache", "faehigkeiten": ["stimme"]})).json()["schluessel"]
        ordner = _agentenordner(tmp_path, url, schluessel, port)
        async with agent_laeuft(ordner):
            async def da():
                return await _modell(c, "probe") is not None
            await _warte_bis(da)
    kopf = {"Authorization": f"Bearer {app_schluessel}"}
    neu = erstellen(Konfig(daten=tmp_path / "daten", oberflaeche=None, dienst_takt_s=0.3))     # derselbe Bestand
    async with laufend(neu) as url, httpx.AsyncClient(base_url=url, timeout=60) as anw:
        r = await anw.get("/v1/dienste/probe/hallo.txt", headers=kopf)
        assert r.status_code == 503 and r.json()["error"]["code"] == "dienst_nicht_erreichbar", r.text
        assert "Mac Studio" in r.json()["error"]["message"] and r.headers["retry-after"]
        r = await anw.post("/v1/chat/completions", headers=kopf, json={"model": "gibts-nicht", "messages": []})
        assert r.json()["error"]["code"] != "kein_modell"                     # auch ein Modellwunsch wartet
        (ordner.wurzel / "einstellungen.toml").write_text((ordner.wurzel / "einstellungen.toml").read_text().replace(
            f'adresse = "{ordner.einstellungen().leitstelle.adresse}"', f'adresse = "{url}"'))   # neue Adresse nach dem Neustart
        async with agent_laeuft(ordner):
            async def wieder():
                return (await anw.get("/v1/dienste/probe/hallo.txt", headers=kopf)).status_code == 200
            await _warte_bis(wieder)
            r = await anw.get("/v1/dienste/gibtsnicht/x", headers=kopf)
            assert r.json()["error"]["code"] == "kein_modell"                 # gemeldet und trotzdem unbekannt: endgültig


async def test_a11_schlaf_ende_zu_ende_mit_dem_echten_maschinenraum(tmp_path):
    """Der Kanal des Maschinenraums meldet den Schlaf, wie es sein Wächter vor dem Einschlafen tut: die Leitstelle
    vermerkt ihn sofort (keine 3 s Wartezeit), Aufträge bekommen 503 rechner_schlaeft; nach dem Aufwachen meldet er
    sich neu, und der Dienst ist wieder nutzbar."""
    from maschinenraum.leitstelle import Verbindung
    from maschinenraum.protokoll import Schlafgrund
    port = _freier_port()
    (tmp_path / "hallo.txt").write_text("Grüße aus dem Dienst")
    async with aufbau(tmp_path) as (c, url, knoten, schluessel):
        app_schluessel = (await c.post("/api/anwendungen", json={"name": "Sprache", "faehigkeiten": ["stimme"]})).json()["schluessel"]
        kopf = {"Authorization": f"Bearer {app_schluessel}"}
        async with agent_laeuft(_agentenordner(tmp_path, url, schluessel, port)) as kanal, httpx.AsyncClient(base_url=url, timeout=60) as anw:
            async def da():
                return await _modell(c, "probe") is not None and kanal.stand.zustand == Verbindung.VERBUNDEN
            await _warte_bis(da)
            beginn = asyncio.get_running_loop().time()
            await kanal.einschlafen(Schlafgrund.LEERLAUF)
            assert asyncio.get_running_loop().time() - beginn < 2.0, "die Leitstelle hat geantwortet"
            assert kanal.stand.zustand == Verbindung.SCHLAEFT
            assert (await _knoten(c, knoten))["zustand"] == "schlaeft"
            r = await anw.get("/v1/dienste/probe/hallo.txt", headers=kopf)
            assert r.status_code == 503 and r.json()["error"]["code"] == "rechner_schlaeft", r.text
            assert r.json()["error"]["x-leitstelle"] == {"rechner": ["Mac Studio"]} and r.headers["retry-after"] == "60"
            await asyncio.sleep(1.5)
            assert not (await _knoten(c, knoten))["agent"]["verbunden"], "solange er schläft, ruht die Verbindung"
            kanal.aufwachen()

            async def wach():
                return (await _knoten(c, knoten))["zustand"] == "erreichbar" and kanal.stand.zustand == Verbindung.VERBUNDEN
            await _warte_bis(wach)
            r = await anw.get("/v1/dienste/probe/hallo.txt", headers=kopf)
            assert r.status_code == 200 and r.content.decode() == "Grüße aus dem Dienst", r.text

