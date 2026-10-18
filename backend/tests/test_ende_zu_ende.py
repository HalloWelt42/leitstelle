"""Ende zu Ende: Leitstelle und Schein-Läufer auf echten Ports, Aufrufe wie von einer Anwendung, die nur die
OpenAI-Schnittstelle kennt (Stufe 1). Szenarien E01 bis E12 aus docs/SZENARIEN.md. Nichts Echtes wird berührt."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from urllib.parse import quote

import httpx
import pytest

from leitstelle.api.app import erstellen
from leitstelle.fach import betrieb as betrieb_modul
from leitstelle.kern.modelle import Regelwerk
from leitstelle.konfig import Konfig
from leitstelle.ports.ablage.datenbank import Datenbank
from leitstelle.ports.ablage.repositorien import Ablage
from leitstelle.ports.dienste.openai_kompatibel import HttpStrom

from schein.laeufer import schein_laeufer
from schein.server import laufend


@asynccontextmanager
async def aufbau(tmp_path, speicher_gb: float = 128.0, regelwerk: Regelwerk | None = None, plaetze: int = 4, **konfig):
    """Schein-Läufer und Leitstelle starten, Rechner, Dienst und Anwendung über die Verwaltung einrichten."""
    if regelwerk is not None:
        db = Datenbank(tmp_path / "leitstelle.sqlite")
        await db.oeffnen()
        await Ablage(db).einstellungen.regelwerk_speichern(regelwerk)
        await db.schliessen()
    laeufer = schein_laeufer()
    async with laufend(laeufer) as laeufer_url:
        k = Konfig(daten=tmp_path, oberflaeche=None, dienst_takt_s=0.3, hinweis_s=1.0, **konfig)
        app = erstellen(k)
        async with laufend(app) as url:
            async with httpx.AsyncClient(base_url=url, timeout=30) as c:
                r = await c.post("/api/dienste", json={"adresse": laeufer_url, "plaetze": plaetze,
                                                         "neuer_knoten": {"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": speicher_gb}})
                assert r.status_code == 200, r.text
                r = await c.post("/api/anwendungen", json={"name": "Codehilfe", "prioritaet": 2})
                assert r.status_code == 200, r.text
                schluessel = r.json()["schluessel"]
                anw = httpx.AsyncClient(base_url=url + "/v1", timeout=30, headers={"Authorization": f"Bearer {schluessel}"})
                try:
                    yield c, anw, laeufer.state.lage, app
                finally:
                    await anw.aclose()


def _sse(text: str) -> list[dict]:
    return [json.loads(z[6:]) for z in text.splitlines() if z.startswith("data: ") and z != "data: [DONE]"]


async def _warte_bis(bedingung, sekunden: float = 10.0):
    for _ in range(int(sekunden * 20)):
        if await bedingung():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Bedingung nicht erreicht")


async def test_e01_strom_an_geladenes_modell_mit_messung(tmp_path):
    async with aufbau(tmp_path) as (c, anw, lage, _):
        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "stream": True, "messages": [{"role": "user", "content": "hallo"}]})
        assert r.status_code == 200 and r.headers["x-leitstelle-lage"] == "ruhig"
        teile = _sse(r.text)
        assert "".join(t["choices"][0]["delta"].get("content", "") for t in teile) == "Stück0 Stück1 Stück2 Stück3 Stück4 "
        assert r.text.rstrip().endswith("data: [DONE]")
        auftrag = r.headers["x-leitstelle-auftrag"]
        await _warte_bis(lambda: _zustand(c, auftrag, "fertig"))
        e = (await c.get(f"/api/auftraege/{auftrag}")).json()
        assert e["token_aus"] == 5 and e["erstes_stueck_s"] is not None and e["modell_name"] == "Qwen3 Next 80B"
        zustaende = [s["zustand"] for s in e["schritte"]]
        assert zustaende[0] == "eingereiht" and "laeuft" in zustaende and zustaende[-1] == "fertig"
        assert "angenommen von Codehilfe" in e["schritte"][0]["text"]
        k = (await c.get("/api/kennzahlen")).json()
        assert k["fertig"] == 1 and k["wartezeit_mittel_s"] is not None
        assert lage.anfragen[-1]["model"] == "qwen/qwen3-next-80b"


async def _zustand(c, auftrag: str, zustand: str) -> bool:
    r = await c.get(f"/api/auftraege/{auftrag}")
    return r.status_code == 200 and r.json()["zustand"] == zustand


async def test_e13_titel_mit_umlauten(tmp_path):
    from urllib.parse import quote
    async with aufbau(tmp_path) as (c, anw, lage, _):
        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []},
                           headers={"X-Leitstelle-Titel": quote("Quelltext prüfen")})
        await _warte_bis(lambda: _zustand(c, r.headers["x-leitstelle-auftrag"], "fertig"))
        e = (await c.get(f"/api/auftraege/{r.headers['x-leitstelle-auftrag']}")).json()
        assert e["titel"] == "Quelltext prüfen"
        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []},
                           headers=[(b"X-Leitstelle-Titel", "Größe prüfen".encode("utf-8"))])
        await _warte_bis(lambda: _zustand(c, r.headers["x-leitstelle-auftrag"], "fertig"))
        e = (await c.get(f"/api/auftraege/{r.headers['x-leitstelle-auftrag']}")).json()
        assert e["titel"] == "Größe prüfen"



async def test_e17_anfragen_einer_arbeit_werden_gezaehlt_und_gemerkt(tmp_path):
    """Kopf X-Leitstelle-Arbeit: die Anfragen einer Arbeit der Anwendung zählen zusammen, ihr Modell gilt als von ihr
    genutzt, der Verlauf trägt die Arbeit; eine Kennung mit unerlaubten Zeichen zählt nicht."""
    async with aufbau(tmp_path) as (c, anw, lage, app):
        for _ in range(2):
            r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []},
                               headers={"X-Leitstelle-Arbeit": "vt-42", "X-Leitstelle-Titel": quote("Vertonung prüfen")})
            await _warte_bis(lambda: _zustand(c, r.headers["x-leitstelle-auftrag"], "fertig"))
        e = (await c.get(f"/api/auftraege/{r.headers['x-leitstelle-auftrag']}")).json()
        arbeit = e["arbeit"]
        assert arbeit.endswith(":vt-42")
        w = app.state.betrieb.verbund.arbeiten[arbeit]
        assert w.anfragen == 2 and w.titel == "Vertonung prüfen"
        assert [app.state.betrieb.verbund.modelle[k].name for k in w.modelle] == [e["modell_name"]] == ["Qwen3 Next 80B"]
        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []}, headers={"X-Leitstelle-Arbeit": "a b"})
        await _warte_bis(lambda: _zustand(c, r.headers["x-leitstelle-auftrag"], "fertig"))
        assert (await c.get(f"/api/auftraege/{r.headers['x-leitstelle-auftrag']}")).json()["arbeit"] is None


async def test_e02_nicht_geladenes_modell_wird_vorher_geladen_und_gemessen(tmp_path):
    async with aufbau(tmp_path) as (c, anw, lage, app):
        bild = [{"role": "user", "content": [{"type": "text", "text": "was ist das"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}]
        r = await anw.post("/chat/completions", json={"model": "glm-4.6v-flash", "messages": bild})   # Name ohne Anbieter wird erkannt
        assert r.status_code == 200, r.text
        assert r.json()["choices"][0]["message"]["content"].startswith("Stück0")
        assert lage.ladevorgaenge == ["zai-org/glm-4.6v-flash"]
        assert r.headers["x-leitstelle-modell"] == "Glm 4.6v Flash"
        mw = app.state.betrieb.messwerk
        assert any(k.startswith("zai-org/glm-4.6v-flash@") for k in mw.ladezeiten)
        e = (await c.get("/api/auftraege")).json()["eintraege"][0]
        assert e["faehigkeit"] == "bild_beschreiben"


async def test_e03_einbettung_und_modellliste(tmp_path):
    async with aufbau(tmp_path) as (c, anw, lage, _):
        r = await anw.post("/embeddings", json={"model": "text-embedding-bge-m3", "input": ["a", "b"]})
        assert r.status_code == 200 and len(r.json()["data"]) == 2
        liste = (await anw.get("/models")).json()["data"]
        ids = {m["id"] for m in liste}
        assert {"qwen/qwen3-next-80b", "zai-org/glm-4.6v-flash", "text-embedding-bge-m3"} <= ids
        v0 = (await c.get("/api/v0/models")).json()["data"]
        assert {m["id"]: m["state"] for m in v0}["qwen/qwen3-next-80b"] == "loaded"
        assert {m["id"]: m["type"] for m in v0}["text-embedding-bge-m3"] == "embeddings"


async def test_e04_ablehnungen_mit_status_und_grund(tmp_path):
    async with aufbau(tmp_path) as (c, anw, lage, _):
        r = await anw.post("/chat/completions", json={"model": "gibt-es-nicht", "messages": []})
        assert r.status_code == 404 and r.json()["error"]["code"] == "kein_modell"
        r = await anw.post("/chat/completions", json={"messages": []})
        assert r.status_code == 404 and "keine Kette" in r.json()["error"]["message"]
        ohne = httpx.AsyncClient(base_url=str(anw.base_url))
        r = await ohne.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []})
        assert r.status_code == 401 and r.json()["error"]["code"] == "unbekannter_schluessel"
        await ohne.aclose()
        assert (await c.post("/api/hauptregler", json={"modus": "halt", "hintergrund": True})).status_code == 200
        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []})
        assert r.status_code == 503 and r.json()["error"]["code"] == "halt" and r.headers["retry-after"] == "30"
        await c.post("/api/hauptregler", json={"modus": "normal", "hintergrund": True})
        anwendung = (await c.get("/api/lage")).json()["anwendungen"][0]["kennung"]
        await c.post(f"/api/anwendungen/{anwendung}/sperren", json={"grund": "Test"})
        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []})
        assert r.status_code == 429 and r.json()["error"]["code"] == "gesperrt"
        await c.post(f"/api/anwendungen/{anwendung}/freigeben")
        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []})
        assert r.status_code == 200
        protokoll = [e["was"] for e in (await c.get("/api/pruefprotokoll")).json()["eintraege"]]
        assert any("Hauptregler" in w for w in protokoll) and "Anwendung freigegeben" in protokoll


async def test_e05_sofort_stoppen_liefert_teiltext(tmp_path):
    async with aufbau(tmp_path) as (c, anw, lage, _):
        lage.stuecke, lage.stueck_pause_s = 200, 0.05
        async with anw.stream("POST", "/chat/completions", json={"model": "qwen/qwen3-next-80b", "stream": True, "messages": []}) as r:
            auftrag = r.headers["x-leitstelle-auftrag"]
            zeilen = []
            async for z in r.aiter_lines():
                zeilen.append(z)
                if len(zeilen) == 10:
                    s = await c.post(f"/api/auftraege/{auftrag}/stoppen", json={"modus": "sofort", "grund": "Test"})
                    assert s.status_code == 200
        teile = _sse("\n".join(zeilen))
        ende = teile[-1]
        assert ende["choices"][0]["finish_reason"] == "leitstelle_abbruch" and ende["x-leitstelle"]["grund"] == "nutzer"
        assert ende["x-leitstelle"]["teilergebnis_zeichen"] > 0
        await _warte_bis(lambda: _zustand(c, auftrag, "abgebrochen"))
        e = (await c.get(f"/api/auftraege/{auftrag}")).json()
        assert e["teilergebnis_zeichen"] > 0 and e["grund"] == "nutzer"
        await _warte_bis(lambda: _wahr(lage.abgebrochen >= 1))


async def _wahr(x: bool) -> bool:
    return x


async def test_e06_anwendung_trennt_waehrend_des_stroms(tmp_path):
    async with aufbau(tmp_path) as (c, anw, lage, app):
        lage.stuecke, lage.stueck_pause_s = 200, 0.05
        async with anw.stream("POST", "/chat/completions", json={"model": "qwen/qwen3-next-80b", "stream": True, "messages": []}) as r:
            auftrag = r.headers["x-leitstelle-auftrag"]
            async for _ in r.aiter_lines():
                break
        await _warte_bis(lambda: _zustand(c, auftrag, "abgebrochen"))
        assert (await c.get(f"/api/auftraege/{auftrag}")).json()["grund"] == "anwendung"
        await _warte_bis(lambda: _wahr(not app.state.betrieb.verbund.auftraege))
        m = next(m for m in app.state.betrieb.verbund.modelle.values() if m.familie == "qwen/qwen3-next-80b")
        assert m.auftraege_aktiv == 0 and m.zustand.value == "geladen", "das Modell ist wieder frei"


async def test_e07_plaetze_werden_eingehalten(tmp_path):
    async with aufbau(tmp_path, plaetze=1) as (c, anw, lage, _):
        lage.stueck_pause_s = 0.05
        antworten = await asyncio.gather(*(anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []}) for _ in range(3)))
        assert all(r.status_code == 200 for r in antworten)
        assert lage.gleichzeitig_hoechst == 1


async def test_e08_speichermangel_beim_laufer_wird_mit_pausen_wiederholt_dann_abgelehnt(tmp_path, monkeypatch):
    monkeypatch.setattr(betrieb_modul, "LADEPAUSEN_S", (0.3, 0.3, 0.3))
    async with aufbau(tmp_path) as (c, anw, lage, app):
        lage.speicher_gb = 50.0           # der Läufer selbst lässt Gemma neben dem 80B nicht zu
        r = await anw.post("/chat/completions", json={"model": "google/gemma-4-26b-a4b-qat", "stream": True, "messages": []})
        assert r.status_code == 200
        assert ": wartet" in r.text, "Hinweise während des Wartens"
        fehler = _sse(r.text)[-1]["error"]
        assert fehler["code"] == "modell_passt_nicht" and "3-mal abgelehnt" in fehler["message"]
        meldungen = [m["text"] for m in (await c.get("/api/lage")).json()["meldungen"]]
        assert any("abgelehnt (zu wenig Speicher)" in m for m in meldungen)


async def test_e09_selbststeuerung_raeumt_leerlauf_fuer_wartenden_auftrag(tmp_path):
    """Echte Kette: Budget des Rechners reicht nicht für Bildmodell neben dem 80B, das 80B ist ungenutzt.
    Die Regel Leerlauf räumen entlädt es über den Läufer, lädt GLM, der Auftrag läuft."""
    r = Regelwerk(bedarfsfrist_s=0, mindestverweildauer_s=0, umschichter_takt_s=0.5)
    async with aufbau(tmp_path, speicher_gb=64.0, regelwerk=r) as (c, anw, lage, _):
        antwort = await anw.post("/chat/completions", json={"model": "zai-org/glm-4.6v-flash", "messages": []})
        assert antwort.status_code == 200, antwort.text
        assert lage.entladevorgaenge == ["qwen/qwen3-next-80b"] and lage.ladevorgaenge == ["zai-org/glm-4.6v-flash"]
        massnahmen = (await c.get("/api/massnahmen")).json()["eintraege"]
        assert any(m["art"] == "leerlauf_raeumen" and m["zustand"] == "ausgefuehrt" for m in massnahmen)



async def test_e18_erst_frei_dann_laden(tmp_path):
    """Das Entladen dauert, und der Läufer lässt GLM neben dem 80B nicht zu: die Leitstelle lädt erst, wenn das Entladen
    zurück ist, im ersten Versuch und ohne Ablehnung (vorher liefen beide nebeneinander, das Laden scheiterte)."""
    r = Regelwerk(bedarfsfrist_s=0, mindestverweildauer_s=0, umschichter_takt_s=0.5)
    async with aufbau(tmp_path, speicher_gb=64.0, regelwerk=r) as (c, anw, lage, _):
        lage.speicher_gb, lage.entladezeit_s = 50.0, 0.4
        antwort = await anw.post("/chat/completions", json={"model": "zai-org/glm-4.6v-flash", "messages": []})
        assert antwort.status_code == 200, antwort.text
        assert lage.entladevorgaenge == ["qwen/qwen3-next-80b"] and lage.ladevorgaenge == ["zai-org/glm-4.6v-flash"]
        meldungen = [m["text"] for m in (await c.get("/api/lage")).json()["meldungen"]]
        assert not any("abgelehnt" in m for m in meldungen), meldungen
        async def zwei_bewegungen() -> bool:          # die Schreibfolge legt sie nebenher ab
            return (await c.get("/api/bewegungen")).json()["gesamt"] == 2
        await _warte_bis(zwei_bewegungen)
        b = (await c.get("/api/bewegungen")).json()
        reihe = [(x["richtung"], x["name"], x["ausgang"]) for x in reversed(b["eintraege"])]
        assert reihe == [("entladen", "Qwen3 Next 80B", "ok"), ("laden", "Glm 4.6v Flash", "ok")], reihe
        entladen, laden = reversed(b["eintraege"])
        assert entladen["dauer_s"] >= 0.4 and laden["zeit_s"] >= entladen["zeit_s"] + entladen["dauer_s"] - 0.01


async def test_e10_vom_dienst_selbst_entladenes_modell_wird_neu_geladen(tmp_path):
    async with aufbau(tmp_path) as (c, anw, lage, app):
        lage.modelle["qwen/qwen3-next-80b"].instanzen.clear()       # Läufer entlädt von sich aus (Leerlauf-Ablauf)
        app.state.betrieb.konfig.dienst_takt_s = 3600                # die Leitstelle merkt es nicht vorher
        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []})
        assert r.status_code == 200, r.text
        assert lage.ladevorgaenge == ["qwen/qwen3-next-80b"]


async def test_e11_heimnetz_schutz_fuer_verwaltung(tmp_path):
    async with aufbau(tmp_path) as (c, anw, lage, app):
        app.state.konfig.erlaubte_netze = ["10.99.0.0/16"]
        assert (await c.get("/api/lage")).status_code == 403
        assert (await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []})).status_code == 200


async def test_e12_kanal_liefert_lagebild_und_ereignisse(tmp_path):
    websockets = pytest.importorskip("websockets")
    async with aufbau(tmp_path) as (c, anw, lage, _):
        ws_url = str(c.base_url).replace("http", "ws") + "/api/kanal"
        async with websockets.connect(ws_url) as ws:
            erstes = json.loads(await ws.recv())
            assert erstes["protokoll"] == "leitstelle/1" and erstes["art"] == "leitstelle.lagebild"
            assert erstes["nutzlast"]["knoten"][0]["name"] == "Mac Studio"
            await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []})
            arten = set()
            for _ in range(30):
                arten.add(json.loads(await asyncio.wait_for(ws.recv(), 5))["art"])
                if "auftrag.ergebnis" in arten:
                    break
            assert {"auftrag.angenommen", "auftrag.ergebnis"} <= arten


async def test_e14_beim_start_geladene_modelle_sind_nicht_frisch(tmp_path):
    """Nach einem Neustart kennt die Leitstelle den Ladezeitpunkt vorhandener Modelle nicht. Die Mindestverweildauer
    (Schutz vor eigenem Hin und Her) gilt für sie nicht; nur die Bedarfsfrist schützt."""
    r = Regelwerk(bedarfsfrist_s=0, umschichter_takt_s=0.5)          # Mindestverweildauer bleibt bei 10 Minuten
    async with aufbau(tmp_path, speicher_gb=64.0, regelwerk=r) as (c, anw, lage, app):
        m = next(m for m in app.state.betrieb.verbund.modelle.values() if m.familie == "qwen/qwen3-next-80b")
        assert m.geladen_seit_s is None
        antwort = await anw.post("/chat/completions", json={"model": "zai-org/glm-4.6v-flash", "messages": []})
        assert antwort.status_code == 200, antwort.text
        assert lage.entladevorgaenge == ["qwen/qwen3-next-80b"]


async def test_e15_kurze_auftraege_stehen_mit_endzustand_im_verlauf(tmp_path, caplog):
    """Vorfall vom 18.10.2026: Aufträge von wenigen Millisekunden (Stimmenliste über die Dienstfassade) und sofort
    abgelehnte blieben im Verlauf auf "laeuft" oder "eingereiht", obwohl sie im Speicher längst fertig waren: das Speichern
    beim Anlegen und beim Abschließen liefen gleichzeitig, das zweite scheiterte am doppelten Schlüssel."""
    async with aufbau(tmp_path) as (c, anw, _, app):
        kurz = await asyncio.gather(*(anw.get("/dienste/qwen3-next-80b/v1/models") for _ in range(60)))
        assert all(r.status_code == 200 for r in kurz)
        abgelehnt = await asyncio.gather(*(anw.post("/chat/completions", json={"messages": []}) for _ in range(20)))
        assert all(r.status_code == 404 for r in abgelehnt)
        await _warte_bis(lambda: _wahr(not app.state.betrieb.verbund.auftraege))
        await app.state.betrieb.schreibfolge.leeren()
        eintraege = (await c.get("/api/auftraege", params={"anzahl": 200})).json()["eintraege"]
        assert sorted(e["zustand"] for e in eintraege) == ["abgelehnt"] * 20 + ["fertig"] * 60
    assert "gescheitert" not in caplog.text


async def _abreissen(url: str, schluessel: str, pfad: str, nach_s: float) -> None:
    """Wie eine Anwendung, die mitten in der Anfrage neu startet: Anfrage schicken, nach `nach_s` die Verbindung schließen."""
    u = httpx.URL(url)
    leser, schreiber = await asyncio.open_connection(u.host, u.port)
    schreiber.write(f"GET {pfad} HTTP/1.1\r\nHost: {u.host}\r\nAuthorization: Bearer {schluessel}\r\n\r\n".encode())
    await schreiber.drain()
    try:
        await asyncio.wait_for(leser.read(64), nach_s)
    except TimeoutError:
        pass
    schreiber.close()


@pytest.mark.parametrize("wann", ["vor_dem_kopf", "im_strom"])
async def test_e16_anwendung_trennt_waehrend_der_durchleitung(tmp_path, monkeypatch, wann):
    """Die Anwendung bricht eine Anfrage über die Dienstfassade ab, während der Dienst noch rechnet (vor dem Antwortkopf)
    oder mitten in seiner Antwort: abgebrochen mit Grund `anwendung` im Verlauf, Speicher leer, das Modell wieder frei.
    Das Schließen der Dienstantwort dauert hier etwas; auch dieses Warten wird beim Abriss abgebrochen."""
    schliessen = HttpStrom.schliessen

    async def langsam_schliessen(self):
        await asyncio.sleep(0.05)
        await schliessen(self)

    monkeypatch.setattr(HttpStrom, "schliessen", langsam_schliessen)
    async with aufbau(tmp_path) as (c, anw, lage, app):
        if wann == "vor_dem_kopf":
            lage.kopf_pause_s = 1.0
        else:
            lage.stuecke, lage.stueck_pause_s = 100, 0.05
        b = app.state.betrieb
        await _abreissen(str(anw.base_url).removesuffix("/v1/"), anw.headers["authorization"][7:],
                         "/v1/dienste/qwen3-next-80b/schein/sprechen", 0.3)
        await _warte_bis(lambda: _wahr(not b.verbund.auftraege))
        await b.schreibfolge.leeren()
        eintrag, = (await c.get("/api/auftraege")).json()["eintraege"]
        assert (eintrag["zustand"], eintrag["grund"]) == ("abgebrochen", "anwendung")
        m = next(m for m in b.verbund.modelle.values() if m.familie == "qwen/qwen3-next-80b")
        assert m.auftraege_aktiv == 0 and m.zustand.value == "geladen", "das Modell ist wieder frei"
        await _warte_bis(lambda: _wahr(lage.abgebrochen == 1), 3.0)      # auch die Antwort des Dienstes ist geschlossen
