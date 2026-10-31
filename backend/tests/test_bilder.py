"""Bilder erzeugen (L1) und die Liste der Dienste (L8): der Bildablauf gegen die Schein-Bildschmiede, die Prüfung der
Anfrage und Ende zu Ende über die Fassade, mit dem echten Maschinenraum, der die Schein-Bildschmiede als Prozess
startet. Die Anwendung kennt nur Beschreibung, Größe, Anzahl und Startwert, nie den Ablauf der Bildschmiede."""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from leitstelle.api.app import erstellen
from leitstelle.konfig import Konfig
from leitstelle.ports.dienste import DienstFehler
from leitstelle.ports.dienste.bilder import Bildauftrag, ComfyAblauf, bildablauf
from leitstelle.ports.dienste.openai_kompatibel import OpenAIKompatibel
from leitstelle.fach.bildregeln import regeln_pruefen
from leitstelle.protokoll.fassade import BildAnfrage, groesse_lesen

from schein.bildschmiede import schein_bildschmiede
from schein.server import laufend

SCHEIN = Path(__file__).resolve().parent / "schein" / "bildschmiede.py"


@asynccontextmanager
async def bildschmiede(rechenzeit_s: float = 0.05):
    """Schein-Bildschmiede auf einem Port und ein `Senden` wie die Durchleitung eines Dienst-Adapters."""
    app = schein_bildschmiede(rechenzeit_s)
    async with laufend(app) as adresse:
        weg = OpenAIKompatibel(adresse)
        try:
            yield app.state.lage, (lambda d: weg.durchleiten("", d))
        finally:
            await weg.schliessen()


def auftrag(**aenderung) -> Bildauftrag:
    return Bildauftrag(**({"beschreibung": "Ein Leuchtturm im Nebel", "breite": 1344, "hoehe": 768, "anzahl": 2, "seed": 42} | aenderung))


async def test_ablauf_erzeugt_mit_dem_graphen_der_bildschmiede_und_ist_wiederholbar():
    async with bildschmiede() as (lage, senden):
        ablauf = bildablauf(ComfyAblauf())
        erstes = await ablauf.erzeugen(senden, auftrag())
        assert len(erstes.bilder) == 2 and all(b.startswith(b"\x89PNG") for b in erstes.bilder) and erstes.seed == 42
        g = lage.graphen[0]
        assert [g[k]["class_type"] for k in sorted(g)] == ["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode", "EmptySD3LatentImage",
                                                           "KSampler", "VAEDecode", "SaveImage"]
        assert g["1"]["inputs"]["ckpt_name"] == "flux1-schnell-fp8.safetensors"
        assert g["4"]["inputs"] == {"width": 1344, "height": 768, "batch_size": 2}
        k = g["5"]["inputs"]
        assert (k["seed"], k["steps"], k["cfg"], k["sampler_name"], k["scheduler"]) == (42, 4, 1.0, "euler", "simple")
        assert (await ablauf.erzeugen(senden, auftrag())).bilder == erstes.bilder              # gleicher Startwert, gleiches Bild
        assert (await ablauf.erzeugen(senden, auftrag(seed=43))).bilder != erstes.bilder


async def test_ablauf_meldet_fehler_der_bildschmiede_im_wortlaut():
    async with bildschmiede() as (_lage, senden):
        with pytest.raises(DienstFehler) as f:
            await bildablauf(ComfyAblauf(checkpoint="gibt-es-nicht.safetensors")).erzeugen(senden, auftrag())
        assert f.value.grund == "dienst_fehler" and "gibt-es-nicht.safetensors" in f.value.meldung
        with pytest.raises(DienstFehler) as f:
            await bildablauf(ComfyAblauf()).erzeugen(senden, auftrag(beschreibung="Fehler beim Rechnen"))
        assert "Speicher erschöpft" in f.value.meldung


async def test_abbruch_traegt_den_auftrag_in_der_bildschmiede_aus():
    async with bildschmiede(rechenzeit_s=30) as (lage, senden):
        arbeit = asyncio.create_task(bildablauf(ComfyAblauf(abfrage_s=0.05)).erzeugen(senden, auftrag()))
        while not lage.aufgaben:
            await asyncio.sleep(0.02)
        arbeit.cancel()
        await asyncio.gather(arbeit, return_exceptions=True)
        kennung = next(iter(lage.aufgaben))
        assert lage.ausgetragen == [kennung] and lage.unterbrochen == [kennung]


def test_ohne_bildablauf_kein_dienst():
    """Ohne eigenen Eintrag gilt die Vorgabe (übliches Bildformat); ist auch die abgeschaltet, bleibt ein Bilddienst nur roh
    durchleitbar, und die Fassade lehnt mit einem Satz ab."""
    from leitstelle.fach.fehler import Ablehnung
    from leitstelle.fach.vermittlung import Vermittlung
    from leitstelle.ports.dienste.bilder.bildformat import Bildformat
    from leitstelle.ports.dienste.bilder.comfyui import Comfy
    assert isinstance(Vermittlung(None, Konfig()).bildablauf_fuer("bildschmiede"), Comfy)  # type: ignore[arg-type]
    assert isinstance(Vermittlung(None, Konfig()).bildablauf_fuer("bildwerk-moss-image"), Bildformat)  # type: ignore[arg-type]
    with pytest.raises(Ablehnung) as a:
        Vermittlung(None, Konfig(bildablaeufe={}, bildablauf_vorgabe=None)).bildablauf_fuer("bildschmiede")  # type: ignore[arg-type]
    assert a.value.grund == "kein_dienst" and "/v1/dienste/bildschmiede/" in a.value.begruendung


def test_anfrage_im_openai_format_wird_geprueft():
    """Die Fassade prüft die Form; ob Größe, Anzahl und Schritte zum Modell passen, sagen die Bildregeln mit seinem Steckbrief."""
    a = BildAnfrage.model_validate({"prompt": "Katze", "size": "768x1344", "quality": "hd", "user": "x"})   # Unbekanntes wird überlesen
    assert (groesse_lesen(a.size), a.n, a.seed, a.steps, a.response_format) == ((768, 1344), 1, None, None, "b64_json")
    assert BildAnfrage.model_validate({"prompt": "x"}).size is None                                    # ohne Größe: Vorgabe des Modells
    for falsch in ({"prompt": " "}, {"prompt": "x", "size": "groß"}, {"prompt": "x", "size": "0x512"}, {"prompt": "x", "n": 5},
                   {"prompt": "x", "response_format": "url"}, {"prompt": "x", "seed": -1}, {"prompt": "x", "steps": 0}, {"size": "1024x1024"}):
        with pytest.raises(ValidationError):
            BildAnfrage.model_validate(falsch)
    # ohne Steckbrief gelten die Vorgabegrenzen der Fassade (Kanten 256 bis 2048, durch 16 teilbar)
    assert "durch 16 teilbar" in regeln_pruefen(None, "1000x1000", 1, None)
    assert regeln_pruefen(None, "256x256", 4, 500) is None


# ── Ende zu Ende mit dem Maschinenraum ──────────────────────────────────
def _ordner(tmp: Path, url: str, schluessel: str, port: int):
    """Maschinenraum mit der Schein-Bildschmiede als Dienst `bildschmiede`; sie braucht 2,5 s zum Starten."""
    o = tmp / "maschinenraum"
    (o / "dienste").mkdir(parents=True)
    (o / "einstellungen.toml").write_text(f'[leitstelle]\nadresse = "{url}"\nwiederverbindung_max_s = 1\n[messung]\ntakt_s = 1\nmacmon = false\n')
    (o / "schluessel").write_text(schluessel)
    (o / "dienste" / "bildschmiede.toml").write_text(
        f'name = "Bildschmiede"\nordner = "{tmp}"\nbefehl = ["{sys.executable}", "{SCHEIN}", "{port}", "0.2", "2.5"]\n'
        f'port = {port}\nfaehigkeiten = ["bild_erzeugen"]\nspeicher_gb = 0.5\nstartzeit_s = 20\nanhaltezeit_s = 5\n')
    from maschinenraum.konfig import Ordner
    return Ordner(o)


@asynccontextmanager
async def aufbau(tmp_path: Path):
    app = erstellen(Konfig(daten=tmp_path / "daten", oberflaeche=None, dienst_takt_s=0.3, hinweis_s=0.5))
    async with laufend(app) as url, httpx.AsyncClient(base_url=url, timeout=30) as c:
        knoten = (await c.post("/api/knoten", json={"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": 64, "system_gb": 6})).json()["kennung"]
        schluessel = (await c.post(f"/api/knoten/{knoten}/agent/schluessel/neu")).json()["schluessel"]
        yield c, url, schluessel


def _sse(text: str) -> tuple[list[str], list[str]]:
    zeilen = [z for z in text.split("\n") if z]
    return [z for z in zeilen if z.startswith(":")], [z[6:] for z in zeilen if z.startswith("data: ")]


async def test_bilder_und_dienste_ueber_die_fassade(tmp_path):
    pytest.importorskip("maschinenraum")
    from test_knoten_agent import _freier_port, _modell, _warte_bis, agent_laeuft
    port = _freier_port()
    async with aufbau(tmp_path) as (c, url, schluessel):
        bild = {"Authorization": f"Bearer {(await c.post('/api/anwendungen', json={'name': 'Bilder', 'faehigkeiten': ['bild_erzeugen'], 'ketten': {'bild_erzeugen': ['bildschmiede']}})).json()['schluessel']}"}
        text = {"Authorization": f"Bearer {(await c.post('/api/anwendungen', json={'name': 'Nur Text', 'faehigkeiten': ['text']})).json()['schluessel']}"}
        async with agent_laeuft(_ordner(tmp_path, url, schluessel, port)):
            async def da():
                return await _modell(c, "bildschmiede") is not None
            await _warte_bis(da)
            async with httpx.AsyncClient(base_url=url, timeout=60) as anw:
                r = await anw.get("/v1/dienste", headers=bild)
                assert r.status_code == 200 and r.json() == {"object": "list", "data": [
                    {"kennung": "bildschmiede", "name": "Bildschmiede", "aufgabe": "Bilderzeugung", "zweck": "", "faehigkeiten": ["bild_erzeugen"], "zustand": "aus", "rechner": ["Mac Studio"],
                     "bild": None}]}
                assert (await anw.get("/v1/dienste", headers=text)).json()["data"] == []      # nur, was die Anwendung nutzen darf
                assert (await anw.get("/v1/dienste", headers={"Authorization": "Bearer falsch"})).status_code == 401

                # Strom: Hinweise, solange die Bildschmiede startet, dann genau eine Antwort und [DONE]
                anfrage = {"prompt": "Ein Leuchtturm im Nebel", "size": "1344x768", "n": 2, "seed": 42}
                r = await anw.post("/v1/images/generations", headers=bild, json=anfrage | {"stream": True})
                assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
                hinweise, daten = _sse(r.text)
                assert any(h.startswith(": wartet, ") for h in hinweise), hinweise
                assert len(daten) == 2 and daten[-1] == "[DONE]"
                strom = json.loads(daten[0])
                assert len(strom["data"]) == 2 and strom["data"][0]["revised_prompt"] is None
                assert base64.b64decode(strom["data"][0]["b64_json"]).startswith(b"\x89PNG")
                assert strom["x-leitstelle"]["seed"] == 42 and strom["x-leitstelle"]["modell"] == "bildschmiede" and strom["x-leitstelle"]["dauer_ms"] >= 0
                assert (strom["x-leitstelle"]["groesse"], strom["x-leitstelle"]["schritte"]) == ("1344x768", 4)      # die Schritte ihres Ablaufs
                assert (await anw.get("/v1/dienste", headers=bild)).json()["data"][0]["zustand"] == "bereit"

                # ohne Strom, gleicher Startwert und gleiche Beschreibung: dieselben Bilder; anderer Startwert: andere
                r = await anw.post("/v1/images/generations", headers=bild, json=anfrage)
                assert r.status_code == 200, r.text
                assert [d["b64_json"] for d in r.json()["data"]] == [d["b64_json"] for d in strom["data"]]
                auftrag = r.headers["x-leitstelle-auftrag"]
                r = await anw.post("/v1/images/generations", headers=bild, json=anfrage | {"seed": 7, "n": 1})
                assert len(r.json()["data"]) == 1 and r.json()["data"][0]["b64_json"] != strom["data"][0]["b64_json"]
                r = await anw.post("/v1/images/generations", headers=bild, json={"prompt": "Katze", "model": "bildschmiede"})
                assert isinstance(r.json()["x-leitstelle"]["seed"], int)                   # ohne Startwert: gezogen und genannt

                # Rechte und Eingabe
                r = await anw.post("/v1/images/generations", headers=text, json=anfrage)
                assert r.status_code == 403 and r.json()["error"]["code"] == "faehigkeit_nicht_erlaubt"
                for falsch in ({"prompt": "x", "size": "1000x1000"}, {"prompt": "x", "response_format": "url"}, {"prompt": "x", "n": 9}):
                    r = await anw.post("/v1/images/generations", headers=bild, json=falsch)
                    assert r.status_code == 400 and r.json()["error"]["code"] == "eingabe", r.text
                r = await anw.post("/v1/images/generations", headers=bild, json={"prompt": "x", "model": "gibtsnicht"})
                assert r.json()["error"]["code"] == "kein_modell"
                assert (await anw.post("/v1/images/generations", json=anfrage)).status_code == 401

            e = (await c.get(f"/api/auftraege/{auftrag}")).json()
            assert e["faehigkeit"] == "bild_erzeugen" and e["zustand"] == "fertig"
