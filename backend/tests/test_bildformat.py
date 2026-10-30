"""Bildweg für Bilddienste im üblichen Bildformat (Szenarien B01 bis B10, docs/SZENARIEN.md Abschnitt 3g).

Der Bildablauf "bildformat" gegen den Schein-Bilddienst (wie ein Dienst des Bildwerks, ohne zu rechnen): Anfrage,
Steckbrief, Fehler je Antwortcode, Abbruch heißt Verbindung schließen; die Bildregeln aus dem Steckbrief; Ende zu Ende über
die Fassade mit dem echten Maschinenraum, der den Schein-Bilddienst als Prozess startet; im Kern ein Bilddienst als
Ressource, die bei Bedarf anderer weicht.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from conftest import ausgefuehrt, welt_mit
from leitstelle.api.app import erstellen
from leitstelle.fach.bildregeln import bildauftrag, regeln_pruefen
from leitstelle.fach.fehler import Ablehnung
from leitstelle.kern.modelle import Dienst, Modell
from leitstelle.kern.werte import Auftragszustand as Z, Faehigkeit as F, Massnahmenart as A, Modellzustand
from leitstelle.konfig import Konfig
from leitstelle.ports.ablage.datenbank import Datenbank
from leitstelle.ports.ablage.repositorien import Ablage
from leitstelle.ports.dienste import DienstFehler
from leitstelle.ports.dienste.bilder import Bildauftrag, BildformatAblauf, bildablauf
from leitstelle.ports.dienste.bilder.bildformat import fehler_aus
from leitstelle.ports.dienste.openai_kompatibel import OpenAIKompatibel
from leitstelle.protokoll.fassade import BildAnfrage
from leitstelle.protokoll.steckbrief import Bildsteckbrief

from schein.bilddienst import schein_bilddienst
from schein.server import laufend

SCHEIN = Path(__file__).resolve().parent / "schein" / "bilddienst.py"
ABLAUF = bildablauf(BildformatAblauf())


@asynccontextmanager
async def bilddienst(rechenzeit_s: float = 0.05, startzeit_s: float = 0.0):
    """Schein-Bilddienst auf einem Port und ein `Senden` wie die Durchleitung eines Dienst-Adapters."""
    app = schein_bilddienst(rechenzeit_s, startzeit_s)
    async with laufend(app) as adresse:
        weg = OpenAIKompatibel(adresse)
        try:
            yield app.state.lage, (lambda d: weg.durchleiten("", d))
        finally:
            await weg.schliessen()


def auftrag(**aenderung) -> Bildauftrag:
    return Bildauftrag(**({"beschreibung": "Ein Leuchtturm im Nebel", "breite": 1344, "hoehe": 768, "anzahl": 2, "seed": 42, "schritte": 8} | aenderung))


async def test_b01_ablauf_erzeugt_im_bildformat_und_ist_wiederholbar():
    """B01: die Anfrage nennt Beschreibung, Größe, Anzahl, Startwert und Schritte, aber kein Modell (der Dienst hält genau
    eins); die Bilder kommen als PNG aus `data[].b64_json`; gleicher Startwert, gleiche Bilder."""
    async with bilddienst() as (lage, senden):
        erstes = await ABLAUF.erzeugen(senden, auftrag())
        assert len(erstes.bilder) == 2 and all(b.startswith(b"\x89PNG") for b in erstes.bilder) and erstes.seed == 42
        assert lage.anfragen[0] == {"prompt": "Ein Leuchtturm im Nebel", "size": "1344x768", "n": 2, "seed": 42, "steps": 8, "model": None,
                                    "response_format": "b64_json"}
        assert (await ABLAUF.erzeugen(senden, auftrag())).bilder == erstes.bilder
        assert (await ABLAUF.erzeugen(senden, auftrag(seed=43))).bilder != erstes.bilder
        await ABLAUF.erzeugen(senden, auftrag(schritte=None, anzahl=1))
        assert "steps" not in {k for k, w in lage.anfragen[-1].items() if w is not None}     # ohne Schritte: die Vorgabe des Dienstes


async def test_b02_steckbrief_aus_der_modellliste():
    """B02: der Steckbrief des Modells aus `GET v1/models`; ein Dienst ohne diesen Weg sagt nichts."""
    async with bilddienst() as (lage, senden):
        s = await ABLAUF.steckbrief(senden)
        assert s is not None and lage.modelle_gelesen == 1
        assert (s.modell, s.name, s.aliase, s.kann_bearbeiten, s.anzahl_max, s.lizenz, s.quantisierung, s.parameter_mrd, s.textkodierer) == \
            ("moss-image", "MOSS-Image-SFT", ["OpenMOSS-Team/MOSS-Image-SFT"], False, 4, "Apache-2.0", "8bit", 4.9, "Qwen3.5-9B")
        assert (s.groessen.pixel_min, s.groessen.kante_max, s.groessen.vorgabe, s.schritte.groesste, s.schritte.vorgabe) == (262144, 2048, "1024x1024", 218, 50)
        assert s.namen() == {"moss-image", "moss-image-sft", "openmoss-team/moss-image-sft"}
    from schein.bildschmiede import schein_bildschmiede          # spricht kein Bildformat: 404 unter /v1/models
    async with laufend(schein_bildschmiede()) as adresse:
        weg = OpenAIKompatibel(adresse)
        try:
            assert await ABLAUF.steckbrief(lambda d: weg.durchleiten("", d)) is None
        finally:
            await weg.schliessen()


async def test_b03_fehler_je_antwortcode():
    """B03: Absagen des Dienstes als Grundwort; eine Absage der Durchleitung (grund und meldung) heißt nicht erreichbar."""
    erwartet = {400: "eingabe", 422: "eingabe", 409: "anderes_modell", 501: "nicht_unterstuetzt", 503: "dienst_nicht_bereit", 499: "abgebrochen",
                500: "dienst_fehler", 404: "dienst_fehler"}
    for status, grund in erwartet.items():
        f = fehler_aus(status, {"detail": "Satz des Dienstes"})
        assert f.grund == grund and "Satz des Dienstes" in f.meldung and f"({status})" in f.meldung
    f = fehler_aus(422, {"detail": [{"loc": ["body", "n"], "msg": "Input should be less than or equal to 4"}]})
    assert f.grund == "eingabe" and "body.n: Input should be less than or equal to 4" in f.meldung
    f = fehler_aus(409, {"grund": "dienst_aus", "meldung": "Bildwerk MOSS-Image läuft nicht (aus)."})
    assert (f.grund, f.wiederholbar) == ("dienst_nicht_erreichbar", True) and "läuft nicht" in f.meldung
    async with bilddienst(startzeit_s=60) as (_lage, senden):
        with pytest.raises(DienstFehler) as e:
            await ABLAUF.erzeugen(senden, auftrag(breite=256, hoehe=256))     # am Leitstand vorbei geprüft: der Dienst sagt 400
        assert e.value.grund == "eingabe" and "262144" in e.value.meldung
        with pytest.raises(DienstFehler) as e:
            await ABLAUF.erzeugen(senden, auftrag())                          # Modell lädt noch
        assert e.value.grund == "dienst_nicht_bereit" and "nicht bereit" in e.value.meldung


async def test_b04_abbruch_schliesst_die_verbindung():
    """B04: wird der Auftrag abgebrochen, schließt der Ablauf die Verbindung; der Dienst sieht das und hört auf."""
    async with bilddienst(rechenzeit_s=30) as (lage, senden):
        arbeit = asyncio.create_task(ABLAUF.erzeugen(senden, auftrag()))
        while not lage.laufend:
            await asyncio.sleep(0.02)
        arbeit.cancel()
        await asyncio.gather(arbeit, return_exceptions=True)
        for _ in range(100):
            if lage.abgebrochen:
                break
            await asyncio.sleep(0.02)
        assert (lage.abgebrochen, lage.laufend, lage.fertig) == (1, 0, 0)


def _steckbrief() -> Bildsteckbrief:
    from schein.bilddienst import STECKBRIEF
    return Bildsteckbrief.model_validate({**STECKBRIEF, "modell": "moss-image"})


def test_b05_bildregeln_aus_dem_steckbrief():
    """B05: Größe, Anzahl und Schritte nach dem Steckbrief; ohne Größe und Schritte die Vorgaben des Modells; ohne Steckbrief
    die Vorgabegrenzen der Fassade, Schritte entscheidet dann der Dienst."""
    s = _steckbrief()
    assert regeln_pruefen(s, "256x256", 1, None) == "Die Fläche muss zwischen 262144 und 4194304 Pixeln liegen; 256x256 hat 65536. Vorgabe von MOSS-Image-SFT: 1024x1024."
    assert regeln_pruefen(s, "1000x1000", 1, None).startswith("Breite und Höhe müssen durch 16 teilbar sein")
    assert regeln_pruefen(s, "4096x1024", 1, None).startswith("Jede Kante 256 bis 2048 Pixel")
    assert regeln_pruefen(s, "1344x768", 4, 218) is None
    assert regeln_pruefen(s, "1344x768", 1, 300) == "Schritte 1 bis 218, nicht 300."
    assert regeln_pruefen(s.model_copy(update={"anzahl_max": 2}), None, 3, None) == "Höchstens 2 Bilder je Anfrage, nicht 3."
    assert regeln_pruefen(None, "256x256", 1, 300) is None
    a = bildauftrag(BildAnfrage(prompt="Katze"), 5, s)
    assert (a.breite, a.hoehe, a.schritte, a.anzahl, a.seed) == (1024, 1024, 50, 1, 5)
    a = bildauftrag(BildAnfrage(prompt="Katze", size="768x1344", steps=12, n=3), 5, None)
    assert (a.breite, a.hoehe, a.schritte, a.anzahl) == (768, 1344, 12, 3)
    assert bildauftrag(BildAnfrage(prompt="Katze"), 5, None).schritte is None
    with pytest.raises(Ablehnung) as e:
        bildauftrag(BildAnfrage(prompt="Katze", size="256x256"), 5, s)
    assert e.value.grund == "eingabe"


async def test_b06_steckbrief_bleibt_ueber_neustarts(tmp_path):
    """B06: gelesene Bild-Steckbriefe stehen in der Ablage (Migration 0012) und gelten nach einem Neustart der Leitstelle."""
    db = Datenbank(tmp_path / "leitstelle.sqlite")
    await db.oeffnen()
    try:
        ablage = Ablage(db)
        s = _steckbrief().model_copy(update={"abgerufen_s": 1234.5})
        await ablage.bildsteckbriefe.speichern("bildwerk-moss-image", s)
        await ablage.bildsteckbriefe.speichern("bildwerk-moss-image", s)          # überschreibt
        assert await ablage.bildsteckbriefe.alle() == {"bildwerk-moss-image": s}
    finally:
        await db.schliessen()


def test_b07_bilddienst_weicht_bei_bedarf_anderer_nie_beim_rechnen():
    """B07: ein Bilddienst des Maschinenraums (24 GB, startet in bis zu 300 s) ist eine Ressource wie jedes Modell: der
    Zuteiler startet ihn für einen Bildauftrag ("wird auf ... gestartet"); braucht danach ein Textauftrag den Platz, weicht
    er nach der Bedarfsfrist (Leerlauf räumen), aber nie, solange er rechnet."""
    w = welt_mit()
    v = w.verbund
    v.knoten["mac-32"].budget_fest_gb = 4.0                          # kein Ausweichen auf den kleinen Mac
    v.knoten["mac-128"].speicher_gb = 130.0                          # Budget 98: 80B (84,7) und Bilddienst (24) passen nicht zusammen
    v.modelle["qwen80@128"].zustand, v.modelle["qwen80@128"].geladen_seit_s = Modellzustand.FREI, None
    v.dienste["mr-128"] = Dienst(kennung="mr-128", name="Dienste auf Mac Studio", knoten="mac-128", art="agent", faehigkeiten={F.BILD_ERZEUGEN})
    v.modelle["moss@128"] = Modell(kennung="moss@128", name="Bildwerk MOSS-Image", dienst="mr-128", familie="bildwerk-moss-image",
                                   faehigkeiten={F.BILD_ERZEUGEN}, gb=24.0, parameter_mrd=0.0, schutz_vorgabe=False)
    w.wahrheit.ladezeit["bildwerk-moss-image@mac-128"] = 120.0
    v.anwendungen["kiste"].faehigkeiten.add(F.BILD_ERZEUGEN)
    v.anwendungen["kiste"].ketten[F.BILD_ERZEUGEN] = ["bildwerk-moss-image"]
    bild = w.auftrag("kiste", F.BILD_ERZEUGEN, laufzeit_s=200)
    w.laufen(5)
    assert v.auftraege[bild.kennung].begruendung.startswith("Bildwerk MOSS-Image wird auf Dienste auf Mac Studio gestartet")
    w.laufen(150)                                                     # gestartet (120 s), rechnet
    assert v.modelle["moss@128"].zustand == Modellzustand.RECHNET
    text = w.auftrag("zusage", F.TEXT, laufzeit_s=5)
    w.laufen(60)
    assert v.modelle["moss@128"].zustand == Modellzustand.RECHNET, "rechnend weicht er nie"
    assert v.auftraege[text.kennung].zustand in (Z.EINGEREIHT, Z.WARTET_SPEICHER)
    w.laufen_bis_fertig(1200)
    assert v.auftraege[bild.kennung].zustand == Z.FERTIG and v.auftraege[text.kennung].zustand == Z.FERTIG
    geraeumt = ausgefuehrt(w, A.LEERLAUF_RAEUMEN)
    assert geraeumt and v.modelle["moss@128"].zustand == Modellzustand.FREI and "Bildwerk MOSS-Image" in geraeumt[0].grund


def test_b10_die_wahl_bleibt_bei_der_anwendung():
    """B10: nennt die Anwendung ein Modell mit Alternativen, gilt ihre Reihenfolge streng: das verlangte, auch wenn es erst
    gestartet werden muss und eine Alternative schon läuft; eine Alternative nur, wenn das verlangte nicht geht (sein Dienst
    ist weg). Nie ein Modell, das die Anwendung nicht genannt hat."""
    from leitstelle.kern.werte import Dienstzustand
    def welt():
        w = welt_mit()
        v = w.verbund
        v.dienste["mr-128"] = Dienst(kennung="mr-128", name="Dienste auf Mac Studio", knoten="mac-128", art="agent", faehigkeiten={F.BILD_ERZEUGEN})
        v.dienste["mr-32"] = Dienst(kennung="mr-32", name="Dienste auf MacBook", knoten="mac-32", art="agent", faehigkeiten={F.BILD_ERZEUGEN})
        for kennung, dienst, familie, gb, zustand in (("moss@128", "mr-128", "bildwerk-moss-image", 24.0, Modellzustand.FREI),
                                                      ("flux@32", "mr-32", "bildwerk-flux", 8.0, Modellzustand.GELADEN),
                                                      ("frei@32", "mr-32", "bildwerk-anderes", 4.0, Modellzustand.GELADEN)):
            v.modelle[kennung] = Modell(kennung=kennung, name=familie, dienst=dienst, familie=familie, faehigkeiten={F.BILD_ERZEUGEN}, gb=gb, parameter_mrd=0.0,
                                        zustand=zustand, schutz_vorgabe=False, geladen_seit_s=-1000 if zustand != Modellzustand.FREI else None)
        v.anwendungen["kiste"].faehigkeiten.add(F.BILD_ERZEUGEN)
        v.modelle["qwen80@128"].zustand, v.modelle["qwen80@128"].geladen_seit_s = Modellzustand.FREI, None   # Platz für den Bilddienst
        return w
    w = welt()
    a = w.auftrag("kiste", F.BILD_ERZEUGEN, laufzeit_s=5, festes_modell="bildwerk-moss-image")
    a.alternativen = ["bildwerk-flux"]
    w.laufen(5)
    assert w.verbund.auftraege[a.kennung].modell == "moss@128", "das verlangte Modell, obwohl die Alternative schon läuft"
    w = welt()
    w.verbund.dienste["mr-128"].zustand = Dienstzustand.NICHT_ERREICHBAR
    a = w.auftrag("kiste", F.BILD_ERZEUGEN, laufzeit_s=5, festes_modell="bildwerk-moss-image")
    a.alternativen = ["bildwerk-flux"]
    w.laufen(5)
    assert w.verbund.auftraege[a.kennung].modell == "flux@32", "das verlangte geht nicht: die Alternative der Anwendung"
    w.laufen_bis_fertig(200)
    assert all(x.modell != "frei@32" for x in w.verbund.auftraege.values()), "nie ein Modell, das die Anwendung nicht genannt hat"


def test_b11_alternativen_nach_den_regeln_der_modelle():
    """B11: nimmt das verlangte Modell die Anfrage nach seinem Steckbrief nicht an, geht es für diese Anfrage nicht: es gilt
    die nächste Alternative der Anwendung; nimmt keines sie an, `eingabe` mit dem Grund des verlangten."""
    from types import SimpleNamespace
    from leitstelle.fach.vermittlung import Vermittlung
    from leitstelle.kern.modelle import Anwendung
    klein = _steckbrief().model_copy(update={"modell": "klein", "name": "Klein", "aliase": [],
                                              "groessen": _steckbrief().groessen.model_copy(update={"kante_max": 1024, "pixel_max": 1024 * 1024})})
    steckbriefe = {"bild-gross": _steckbrief(), "bild-klein": klein}
    b = SimpleNamespace(familie_fuer=lambda n: n if n in steckbriefe else None, bildsteckbriefe=steckbriefe,
                        unbekannt=lambda n, was: Ablehnung("kein_modell", f"{was} {n} ist im Verbund nicht bekannt."),
                        verbund=SimpleNamespace(anwendungen={"app": Anwendung(kennung="app", name="App", faehigkeiten={F.BILD_ERZEUGEN})}))
    verm = Vermittlung(b, Konfig())  # type: ignore[arg-type]
    wahl = lambda **x: verm.bildwahl("app", BildAnfrage(prompt="x", **x))
    assert wahl(model="bild-klein", alternativen=["bild-gross"]) == ("bild-klein", ["bild-gross"])
    assert wahl(model="bild-klein", alternativen=["bild-gross"], size="2048x1024") == ("bild-gross", [])
    with pytest.raises(Ablehnung) as e:
        wahl(model="bild-klein", alternativen=["bild-gross"], size="256x256")
    assert e.value.grund == "eingabe" and "Fläche" in e.value.begruendung


# ── Ende zu Ende mit dem Maschinenraum ──────────────────────────────────
def _ordner(tmp: Path, url: str, schluessel: str, port: int, rechenzeit_s: float, startzeit_s: float):
    """Maschinenraum mit dem Schein-Bilddienst als `bildwerk-moss-image`; Beobachtung, Läufer und Stellwerk aus, damit der
    Test nichts vom Rechner liest, auf dem er läuft."""
    o = tmp / "maschinenraum"
    (o / "dienste").mkdir(parents=True)
    (o / "einstellungen.toml").write_text(f'[leitstelle]\nadresse = "{url}"\nwiederverbindung_max_s = 1\n[messung]\ntakt_s = 1\nmacmon = false\n'
                                          f'[beobachtung]\naktiv = false\n[nachbar]\nmodell_laeufer = ""\nstellwerk = ""\n')
    (o / "schluessel").write_text(schluessel)
    (o / "dienste" / "bildwerk-moss-image.toml").write_text(
        f'name = "Bildwerk MOSS-Image"\nbeschreibung = "Bilder aus Text mit MOSS-Image: lange Beschreibungen, Schrift im Bild"\n'
        f'ordner = "{tmp}"\nbefehl = ["{sys.executable}", "{SCHEIN}", "{port}", "{rechenzeit_s}", "{startzeit_s}"]\n'
        f'port = {port}\npruefadresse = "http://127.0.0.1:{port}/gesundheit"\nfaehigkeiten = ["bild_erzeugen"]\neignung = ["gruendlich"]\n'
        f'sprachen = ["en", "zh"]\nspeicher_gb = 24\nstartzeit_s = 60\nanhaltezeit_s = 5\n')
    from maschinenraum.konfig import Ordner
    return Ordner(o)


@asynccontextmanager
async def aufbau(tmp_path: Path, rechenzeit_s: float = 0.2, startzeit_s: float = 2.5):
    pytest.importorskip("maschinenraum")
    from test_knoten_agent import _freier_port, _modell, _warte_bis, agent_laeuft
    port = _freier_port()
    app = erstellen(Konfig(daten=tmp_path / "daten", oberflaeche=None, dienst_takt_s=0.3, hinweis_s=0.5))
    async with laufend(app) as url, httpx.AsyncClient(base_url=url, timeout=60) as c:
        knoten = (await c.post("/api/knoten", json={"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": 64, "system_gb": 6})).json()["kennung"]
        schluessel = (await c.post(f"/api/knoten/{knoten}/agent/schluessel/neu")).json()["schluessel"]
        r = await c.post("/api/anwendungen", json={"name": "Assistent", "faehigkeiten": ["text", "bild_erzeugen"]})
        kopf = {"Authorization": f"Bearer {r.json()['schluessel']}"}
        async with agent_laeuft(_ordner(tmp_path, url, schluessel, port, rechenzeit_s, startzeit_s)):
            async def da():
                return await _modell(c, "bildwerk-moss-image") is not None
            await _warte_bis(da)
            async with httpx.AsyncClient(base_url=url, timeout=120) as anw, httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=10) as dienst:
                yield c, anw, kopf, dienst


def _sse(text: str) -> tuple[list[str], list[str]]:
    zeilen = [z for z in text.split("\n") if z]
    return [z for z in zeilen if z.startswith(":")], [z[6:] for z in zeilen if z.startswith("data: ")]


async def test_b08_moss_image_ueber_die_fassade(tmp_path):
    """B08: eine App verlangt den Bilddienst mit `model`; die Leitstelle startet ihn über den Maschinenraum (Wartende sehen,
    seit wann er startet), liest nach dem Start seinen Steckbrief und prüft damit jede weitere Anfrage, bevor sie ihn
    erreicht; das Modell heißt auch mit seinem eigenen Namen; ohne Größe und Schritte gelten die Vorgaben des Modells."""
    async with aufbau(tmp_path) as (c, anw, kopf, dienst):
        m = next(x for x in (await anw.get("/v1/models", headers=kopf)).json()["data"] if x["id"] == "bildwerk-moss-image")
        assert m["x-leitstelle"]["steckbrief"]["bild"] is None and m["x-leitstelle"]["geladen"] is False
        d = (await anw.get("/v1/dienste", headers=kopf)).json()["data"]
        assert d == [{"kennung": "bildwerk-moss-image", "name": "Bildwerk MOSS-Image", "faehigkeiten": ["bild_erzeugen"], "zustand": "aus",
                      "zweck": "Bilder aus Text mit MOSS-Image: lange Beschreibungen, Schrift im Bild", "rechner": ["Mac Studio"], "bild": None}]

        # vor dem ersten Start: die Vorgabegrenzen der Fassade, kein Start für eine Größe, die keiner annimmt
        r = await anw.post("/v1/images/generations", headers=kopf, json={"prompt": "x", "model": "bildwerk-moss-image", "size": "4096x4096"})
        assert r.status_code == 400 and r.json()["error"]["code"] == "eingabe" and "2048" in r.json()["error"]["message"]
        assert (await anw.get("/v1/dienste", headers=kopf)).json()["data"][0]["zustand"] == "aus"

        # erster Auftrag im Strom: Hinweise, solange der Dienst startet, dann genau eine Antwort
        anfrage = {"prompt": "Ein Leuchtturm im Nebel", "model": "bildwerk-moss-image", "size": "1344x768", "n": 2, "seed": 42, "steps": 8}
        r = await anw.post("/v1/images/generations", headers=kopf, json=anfrage | {"stream": True})
        hinweise, daten = _sse(r.text)
        assert any(h.startswith(": wartet, Bildwerk MOSS-Image startet auf Mac Studio seit ") and "Startdauer noch nicht gemessen" in h
                   for h in hinweise), hinweise
        strom = json.loads(daten[0])
        assert daten[-1] == "[DONE]" and len(strom["data"]) == 2 and base64.b64decode(strom["data"][0]["b64_json"]).startswith(b"\x89PNG")
        assert {k: strom["x-leitstelle"][k] for k in ("seed", "modell", "groesse", "schritte")} == \
            {"seed": 42, "modell": "bildwerk-moss-image", "groesse": "1344x768", "schritte": 8}
        gesehen = (await dienst.get("/lage")).json()
        assert gesehen["anfragen"][-1] == {"prompt": "Ein Leuchtturm im Nebel", "size": "1344x768", "n": 2, "seed": 42, "steps": 8, "model": None,
                                           "response_format": "b64_json"}
        assert gesehen["modelle_gelesen"] >= 1

        # nach dem Start: der Steckbrief ist da (Fassade, Liste der Dienste, Steckbriefe, Verlauf)
        m = next(x for x in (await anw.get("/v1/models", headers=kopf)).json()["data"] if x["id"] == "bildwerk-moss-image")
        s = m["x-leitstelle"]["steckbrief"]
        assert (s["bild"]["modell"], s["bild"]["groessen"]["pixel_min"], s["bild"]["schritte"]["groesste"], s["herkunft"]["bild"]) == \
            ("moss-image", 262144, 218, "dienst")
        assert (s["parameter_mrd"], s["quantisierung"], s["eignung"], s["sprachen"]) == (4.9, "8bit", ["gruendlich"], ["en", "zh"])
        assert (await anw.get("/v1/dienste", headers=kopf)).json()["data"][0]["bild"]["name"] == "MOSS-Image-SFT"
        liste = (await anw.get("/v1/steckbriefe", params={"faehigkeit": "bild_erzeugen"}, headers=kopf)).json()["data"]
        assert [x["id"] for x in liste] == ["bildwerk-moss-image"] and liste[0]["steckbrief"]["bild"]["anzahl_max"] == 4
        assert any(z["text"].startswith("Steckbrief von Bildwerk MOSS-Image gelesen: MOSS-Image-SFT; Kanten 256 bis 2048 Pixel")
                   for z in (await c.get("/api/lage")).json()["meldungen"])

        # gleicher Startwert, gleiche Bilder; das Modell auch mit seinem eigenen Namen; ohne Größe und Schritte die Vorgaben
        r = await anw.post("/v1/images/generations", headers=kopf, json=anfrage)
        assert r.status_code == 200 and [x["b64_json"] for x in r.json()["data"]] == [x["b64_json"] for x in strom["data"]]
        for name in ("moss-image", "MOSS-Image-SFT", "OpenMOSS-Team/MOSS-Image-SFT"):
            r = await anw.post("/v1/images/generations", headers=kopf, json={"prompt": "Katze", "model": name})
            assert r.status_code == 200, r.text
            assert {k: r.json()["x-leitstelle"][k] for k in ("modell", "groesse", "schritte")} == \
                {"modell": "bildwerk-moss-image", "groesse": "1024x1024", "schritte": 50}
        assert {k: (await dienst.get("/lage")).json()["anfragen"][-1][k] for k in ("size", "steps", "model")} == \
            {"size": "1024x1024", "steps": 50, "model": None}

        # Grenzen aus dem Steckbrief, geprüft in der Leitstelle: der Dienst sieht diese Anfragen nie
        vorher = len((await dienst.get("/lage")).json()["anfragen"])
        for falsch, satz in (({"size": "256x256"}, "Die Fläche muss zwischen 262144 und 4194304 Pixeln liegen"), ({"steps": 300}, "Schritte 1 bis 218"),
                             ({"size": "1000x1000"}, "durch 16 teilbar")):
            r = await anw.post("/v1/images/generations", headers=kopf, json={"prompt": "x", "model": "moss-image"} | falsch)
            assert r.status_code == 400 and r.json()["error"]["code"] == "eingabe" and satz in r.json()["error"]["message"], r.text
        assert len((await dienst.get("/lage")).json()["anfragen"]) == vorher

        # Das Modell wählt die Anwendung: ohne model und ohne hinterlegte Kette sucht die Leitstelle keines aus
        r = await anw.post("/v1/images/generations", headers=kopf, json={"prompt": "x"})
        assert r.status_code == 400 and r.json()["error"]["code"] == "modell_fehlt", r.text
        assert r.json()["error"]["x-leitstelle"] == {"modelle": ["bildwerk-moss-image"]} and "Bildmodell angeben" in r.json()["error"]["message"]
        r = await anw.post("/v1/images/generations", headers=kopf, json={"prompt": "x", "alternativen": ["moss-image"]})
        assert r.status_code == 400 and r.json()["error"]["code"] == "eingabe"
        r = await anw.post("/v1/images/generations", headers=kopf, json={"prompt": "x", "model": "moss-image", "alternativen": ["gibtsnicht"]})
        assert r.status_code == 404 and r.json()["error"]["code"] == "kein_modell" and "gibtsnicht" in r.json()["error"]["message"]


async def test_b09_abbruch_und_fehler_des_bilddienstes(tmp_path):
    """B09: von Hand gestoppt, während der Bilddienst rechnet: die App bekommt 409 `nutzer`, der Auftrag ist abgebrochen, die
    Leitstelle schließt ihre Verbindung, das Modell ist wieder frei. Ein Fehler des Dienstes kommt mit Grundwort und
    seinem Satz an (502 `dienst_fehler`), der Auftrag ist fehlgeschlagen."""
    async with aufbau(tmp_path, rechenzeit_s=20, startzeit_s=0.5) as (c, anw, kopf, dienst):
        arbeit = asyncio.create_task(anw.post("/v1/images/generations", headers=kopf, json={"prompt": "lang", "model": "bildwerk-moss-image"}))
        for _ in range(400):
            if await _laeuft(dienst) and (await dienst.get("/lage")).json()["laufend"]:
                break
            await asyncio.sleep(0.05)
        offen = [a for a in (await c.get("/api/lage")).json()["auftraege"] if a["faehigkeit"] == "bild_erzeugen"]
        assert len(offen) == 1 and offen[0]["zustand"] == "laeuft"
        r = await c.post(f"/api/auftraege/{offen[0]['kennung']}/stoppen", json={"modus": "sofort", "grund": "Probe"})
        assert r.status_code == 200
        r = await asyncio.wait_for(arbeit, 10)
        assert r.status_code == 409 and r.json()["error"]["code"] == "nutzer"
        e = (await c.get(f"/api/auftraege/{offen[0]['kennung']}")).json()
        assert e["zustand"] == "abgebrochen" and e["grund"] == "nutzer"
        m = next(x for x in (await c.get("/api/lage")).json()["modelle"] if x["familie"] == "bildwerk-moss-image")
        assert m["zustand"] == "geladen" and m["auftraege_aktiv"] == 0
        # der Abbruch reicht durch die Durchleitung des Maschinenraums bis zum Dienst: er hört auf zu rechnen (HELF-24;
        # bis Maschinenraum 0.17.2 wartete die Durchleitung auf seine Antwort und er rechnete zu Ende)
        await _dienst_hat_abgebrochen(dienst, 1)

    async with aufbau(tmp_path / "fehler", rechenzeit_s=0.1, startzeit_s=0.5) as (c, anw, kopf, _dienst):
        r = await anw.post("/v1/images/generations", headers=kopf, json={"prompt": "Fehler beim Rechnen", "model": "bildwerk-moss-image"})
        assert r.status_code == 502 and r.json()["error"]["code"] == "dienst_fehler" and "Speicher erschöpft" in r.json()["error"]["message"]
        e = await _endzustand(c, r.headers["x-leitstelle-auftrag"])
        assert (e["zustand"], e["grund"]) == ("fehlgeschlagen", "dienst_fehler") and "(500)" in e["begruendung"]


async def _endzustand(c: httpx.AsyncClient, kennung: str) -> dict:
    """Der Auftrag mit seinem Endzustand: die Ablage schreibt ihn im Hintergrund (Schreibfolge), kurz nach der Antwort."""
    e = {}
    for _ in range(100):
        e = (await c.get(f"/api/auftraege/{kennung}")).json()
        if e.get("zustand") in ("fertig", "abgebrochen", "fehlgeschlagen", "abgelehnt"):
            break
        await asyncio.sleep(0.05)
    return e


async def _dienst_hat_abgebrochen(dienst: httpx.AsyncClient, anzahl: int) -> None:
    """Der Schein-Bilddienst hat so viele Rechnungen abgebrochen, weil seine Verbindung zuging, und rechnet nichts mehr."""
    lage = {}
    for _ in range(100):
        lage = (await dienst.get("/lage")).json()
        if lage["abgebrochen"] >= anzahl and not lage["laufend"]:
            break
        await asyncio.sleep(0.05)
    assert (lage["abgebrochen"], lage["laufend"], lage["fertig"]) == (anzahl, 0, 0), lage


async def _bis_der_dienst_rechnet(c: httpx.AsyncClient, dienst: httpx.AsyncClient) -> str:
    for _ in range(400):
        if await _laeuft(dienst) and (await dienst.get("/lage")).json()["laufend"]:
            break
        await asyncio.sleep(0.05)
    offen = [a for a in (await c.get("/api/lage")).json()["auftraege"] if a["faehigkeit"] == "bild_erzeugen" and a["zustand"] == "laeuft"]
    assert len(offen) == 1
    return offen[0]["kennung"]


@pytest.mark.parametrize("strom", [True, False])
async def test_b12_anwendung_geht_und_der_bilddienst_hoert_auf(tmp_path, strom):
    """B12 (HELF-24): bricht die Anwendung ab (Verbindung zu), während der Bilddienst rechnet, endet ihr Auftrag in der
    Leitstelle, und der Abbruch reicht über die Durchleitung des Maschinenraums bis zum Dienst: er hört sofort auf. Mit
    Strom und ohne; ohne Strom sah die Leitstelle das Gehen bis 0.26.0 nur, solange der Auftrag noch wartete."""
    async with aufbau(tmp_path, rechenzeit_s=30, startzeit_s=0.5) as (c, anw, kopf, dienst):
        arbeit = asyncio.create_task(anw.post("/v1/images/generations", headers=kopf,
                                              json={"prompt": "lang", "model": "bildwerk-moss-image", "stream": strom}))
        kennung = await _bis_der_dienst_rechnet(c, dienst)
        arbeit.cancel()                                        # die Anwendung geht: ihre Verbindung ist zu
        with pytest.raises(asyncio.CancelledError):
            await arbeit
        await _dienst_hat_abgebrochen(dienst, 1)
        e = await _endzustand(c, kennung)
        assert (e["zustand"], e["grund"]) == ("abgebrochen", "anwendung"), e
        m = next(x for x in (await c.get("/api/lage")).json()["modelle"] if x["familie"] == "bildwerk-moss-image")
        assert m["zustand"] == "geladen" and m["auftraege_aktiv"] == 0


async def _laeuft(dienst: httpx.AsyncClient) -> bool:
    try:
        return (await dienst.get("/gesundheit")).status_code == 200
    except httpx.HTTPError:
        return False
