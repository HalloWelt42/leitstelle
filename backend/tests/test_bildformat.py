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
from pydantic import ValidationError

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


def test_b02b_aufgabenvorlagen_gehen_unveraendert_weiter():
    """B02b (ATL-26 des Ateliers): die Aufgabenvorlagen des Modells (Anweisung mit {wunsch}, Sprache, Signalfarbe) kommen
    unverändert in den Steckbrief; ein Dienst ohne Vorlagen hat keine; eine falsche Signalfarbe macht ihn unlesbar."""
    from schein.bilddienst import STECKBRIEF
    vorlagen = {"entfernen": {"anweisung": "Fill the magenta area.", "sprache": "en", "signalfarbe": [255, 0, 255]},
                "fuellen": {"anweisung": "Replace it with: {wunsch}.", "ohne_wunsch": "Replace it.", "sprache": "en", "signalfarbe": [255, 0, 255]}}
    s = Bildsteckbrief.model_validate({**STECKBRIEF, "modell": "qwen", "aufgaben": vorlagen})
    assert s.model_dump(mode="json")["aufgaben"] == {
        "entfernen": {"anweisung": "Fill the magenta area.", "ohne_wunsch": None, "sprache": "en", "signalfarbe": [255, 0, 255]},
        "fuellen": {"anweisung": "Replace it with: {wunsch}.", "ohne_wunsch": "Replace it.", "sprache": "en", "signalfarbe": [255, 0, 255]}}
    assert Bildsteckbrief.model_validate({**STECKBRIEF, "modell": "moss"}).aufgaben == {}
    with pytest.raises(ValidationError):
        Bildsteckbrief.model_validate({**STECKBRIEF, "modell": "qwen", "aufgaben": {"fuellen": {"anweisung": "x", "sprache": "englisch"}}})


async def test_b03_fehler_je_antwortcode():
    """B03: Absagen des Dienstes als Grundwort; eine Absage der Durchleitung (grund und meldung) heißt nicht erreichbar."""
    erwartet = {400: "eingabe", 422: "eingabe", 409: "anderes_modell", 501: "nicht_unterstuetzt", 503: "dienst_nicht_bereit", 499: "abgebrochen",
                500: "dienst_fehler", 404: "dienst_fehler"}
    for status, grund in erwartet.items():
        f = fehler_aus(status, {"detail": "Satz des Dienstes"})
        assert f.grund == grund and "Satz des Dienstes" in f.meldung and f"({status})" in f.meldung
    f = fehler_aus(422, {"detail": [{"loc": ["body", "n"], "msg": "Input should be less than or equal to 4"}]})
    assert f.grund == "eingabe" and "body.n: Input should be less than or equal to 4" in f.meldung
    f = fehler_aus(409, {"grund": "dienst_aus", "meldung": "MOSS-Image läuft nicht (aus)."})
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
    v.modelle["moss@128"] = Modell(kennung="moss@128", name="MOSS-Image", dienst="mr-128", familie="bildwerk-moss-image",
                                   faehigkeiten={F.BILD_ERZEUGEN}, gb=24.0, parameter_mrd=0.0, schutz_vorgabe=False)
    w.wahrheit.ladezeit["bildwerk-moss-image@mac-128"] = 120.0
    v.anwendungen["kiste"].faehigkeiten.add(F.BILD_ERZEUGEN)
    v.anwendungen["kiste"].ketten[F.BILD_ERZEUGEN] = ["bildwerk-moss-image"]
    bild = w.auftrag("kiste", F.BILD_ERZEUGEN, laufzeit_s=200)
    w.laufen(5)
    assert v.auftraege[bild.kennung].begruendung.startswith("MOSS-Image wird auf Dienste auf Mac Studio gestartet")
    w.laufen(150)                                                     # gestartet (120 s), rechnet
    assert v.modelle["moss@128"].zustand == Modellzustand.RECHNET
    text = w.auftrag("zusage", F.TEXT, laufzeit_s=5)
    w.laufen(60)
    assert v.modelle["moss@128"].zustand == Modellzustand.RECHNET, "rechnend weicht er nie"
    assert v.auftraege[text.kennung].zustand in (Z.EINGEREIHT, Z.WARTET_SPEICHER)
    w.laufen_bis_fertig(1200)
    assert v.auftraege[bild.kennung].zustand == Z.FERTIG and v.auftraege[text.kennung].zustand == Z.FERTIG
    geraeumt = ausgefuehrt(w, A.LEERLAUF_RAEUMEN)
    assert geraeumt and v.modelle["moss@128"].zustand == Modellzustand.FREI and "MOSS-Image" in geraeumt[0].grund


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
def _ordner(tmp: Path, url: str, schluessel: str, port: int, rechenzeit_s: float, startzeit_s: float, bearbeiten: bool = False):
    """Maschinenraum mit dem Schein-Bilddienst als `bildwerk-moss-image`; Beobachtung, Läufer und Stellwerk aus, damit der
    Test nichts vom Rechner liest, auf dem er läuft."""
    o = tmp / "maschinenraum"
    (o / "dienste").mkdir(parents=True)
    (o / "einstellungen.toml").write_text(f'[leitstelle]\nadresse = "{url}"\nwiederverbindung_max_s = 1\n[messung]\ntakt_s = 1\nmacmon = false\n'
                                          f'[beobachtung]\naktiv = false\n[nachbar]\nmodell_laeufer = ""\nstellwerk = ""\n')
    (o / "schluessel").write_text(schluessel)
    zusatz = ', "bearbeiten"' if bearbeiten else ""                # der Schein nimmt dann Bildvorlagen an
    (o / "dienste" / "bildwerk-moss-image.toml").write_text(
        f'name = "MOSS-Image"\nbeschreibung = "Bilder aus Text mit MOSS-Image: lange Beschreibungen, Schrift im Bild"\n'
        f'ordner = "{tmp}"\nbefehl = ["{sys.executable}", "{SCHEIN}", "{port}", "{rechenzeit_s}", "{startzeit_s}"{zusatz}]\n'
        f'port = {port}\npruefadresse = "http://127.0.0.1:{port}/gesundheit"\nfaehigkeiten = ["bild_erzeugen"]\neignung = ["gruendlich"]\n'
        f'sprachen = ["en", "zh"]\nspeicher_gb = 24\nstartzeit_s = 60\nanhaltezeit_s = 5\n')
    from maschinenraum.konfig import Ordner
    return Ordner(o)


@asynccontextmanager
async def aufbau(tmp_path: Path, rechenzeit_s: float = 0.2, startzeit_s: float = 2.5, bearbeiten: bool = False,
                 faehigkeiten: tuple[str, ...] = ("text", "bild_erzeugen")):
    pytest.importorskip("maschinenraum")
    from test_knoten_agent import _freier_port, _modell, _warte_bis, agent_laeuft
    port = _freier_port()
    app = erstellen(Konfig(daten=tmp_path / "daten", oberflaeche=None, dienst_takt_s=0.3, hinweis_s=0.5))
    async with laufend(app) as url, httpx.AsyncClient(base_url=url, timeout=60) as c:
        knoten = (await c.post("/api/knoten", json={"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": 64, "system_gb": 6})).json()["kennung"]
        schluessel = (await c.post(f"/api/knoten/{knoten}/agent/schluessel/neu")).json()["schluessel"]
        r = await c.post("/api/anwendungen", json={"name": "Assistent", "faehigkeiten": list(faehigkeiten)})
        kopf = {"Authorization": f"Bearer {r.json()['schluessel']}"}
        async with agent_laeuft(_ordner(tmp_path, url, schluessel, port, rechenzeit_s, startzeit_s, bearbeiten)):
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
        # HELF-84: der echte Modellname, die Aufgabe kommt vom Maschinenraum aus der Fähigkeit; die Kennung bleibt
        assert m["x-leitstelle"]["name"] == "MOSS-Image" and m["x-leitstelle"]["aufgabe"] == "Bilderzeugung"
        assert d == [{"kennung": "bildwerk-moss-image", "name": "MOSS-Image", "aufgabe": "Bilderzeugung", "faehigkeiten": ["bild_erzeugen"], "zustand": "aus",
                      "zweck": "Bilder aus Text mit MOSS-Image: lange Beschreibungen, Schrift im Bild", "rechner": ["Mac Studio"], "bild": None}]

        # vor dem ersten Start: die Vorgabegrenzen der Fassade, kein Start für eine Größe, die keiner annimmt
        r = await anw.post("/v1/images/generations", headers=kopf, json={"prompt": "x", "model": "bildwerk-moss-image", "size": "4096x4096"})
        assert r.status_code == 400 and r.json()["error"]["code"] == "eingabe" and "2048" in r.json()["error"]["message"]
        assert (await anw.get("/v1/dienste", headers=kopf)).json()["data"][0]["zustand"] == "aus"

        # erster Auftrag im Strom: Hinweise, solange der Dienst startet, dann genau eine Antwort
        anfrage = {"prompt": "Ein Leuchtturm im Nebel", "model": "bildwerk-moss-image", "size": "1344x768", "n": 2, "seed": 42, "steps": 8}
        r = await anw.post("/v1/images/generations", headers=kopf, json=anfrage | {"stream": True})
        hinweise, daten = _sse(r.text)
        assert any(h.startswith(": wartet, MOSS-Image startet auf Mac Studio seit ") and "Startdauer noch nicht gemessen" in h
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
        assert any(z["text"].startswith("Steckbrief von MOSS-Image gelesen: MOSS-Image-SFT; Kanten 256 bis 2048 Pixel")
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


async def test_b13_bildablage_begrenzt_und_quittiert(tmp_path):
    """B13: die Bildablage (PROTOKOLL 6.3, Migration 0013) legt nur ab, wenn es ein Archiv gibt und der Erzeuger keines
    ist; über der Grenze fallen die ältesten weg; Quittieren nimmt Datei und Eintrag."""
    from leitstelle.fach.bildablage import Bildablage
    from leitstelle.ports.ablage.eintraege import AnwendungEintrag
    from leitstelle.ports.dienste.bilder.schnittstelle import Bildergebnis
    db = Datenbank(tmp_path / "leitstelle.sqlite")
    await db.oeffnen()
    try:
        ablage = Bildablage(Ablage(db).bildablage, tmp_path / "bildablage", grenze_mb=1)
        app = lambda k, archiv=False: AnwendungEintrag(kennung=k, name=k, schluessel_fingerabdruck=k, schluessel_geheim="",  # noqa: E731
                                                       faehigkeiten={F.BILD_ERZEUGEN}, bildarchiv=archiv)
        maler, archiv = app("maler"), app("archiv", True)
        auftrag = Bildauftrag(beschreibung="Ein Leuchtturm", breite=64, hoehe=64, anzahl=2, seed=7)
        ergebnis = Bildergebnis(bilder=[b"\x89PNG" + b"a" * 600_000, b"\x89PNG" + b"b" * 600_000], seed=7, schritte=4)
        assert await ablage.ablegen(maler, [maler], "a1", auftrag, ergebnis, "moss", 1.0) == 0        # ohne Archiv nichts
        assert await ablage.ablegen(archiv, [maler, archiv], "a2", auftrag, ergebnis, "moss", 2.0) == 0   # das Archiv hat seine schon
        assert await ablage.ablegen(maler, [maler, archiv], "a3", auftrag, ergebnis, "moss", 3.0) == 2
        bilder, wartend, belegt = await ablage.wartend(10)
        assert wartend == 1 and belegt < 1024 * 1024        # zwei Bilder zu 600 kB passen nicht in 1 MB: das ältere ist weg
        e = bilder[0]
        assert (e.anwendung, e.auftrag, e.beschreibung, e.seed, e.nummer, e.familie, e.schritte) == ("maler", "a3", "Ein Leuchtturm", 7, 1, "moss", 4)
        assert (await ablage.datei(e.kennung))[1].startswith(b"\x89PNGb")
        assert await ablage.quittieren(e.kennung) and await ablage.datei(e.kennung) is None
        assert not (tmp_path / "bildablage" / f"{e.kennung}.png").exists() and not await ablage.quittieren(e.kennung)
    finally:
        await db.schliessen()


async def test_b14_bildarchiv_holt_ueber_die_fassade_ab(tmp_path):
    """B14: ein Bild, das eine Anwendung erzeugt, wartet auf das Archiv; nur das Archiv sieht, holt und quittiert es."""
    async with aufbau(tmp_path) as (c, anw, kopf, dienst):
        r = await c.post("/api/anwendungen", json={"name": "Bildarchiv", "faehigkeiten": ["bild_erzeugen"], "bildarchiv": True})
        archiv = {"Authorization": f"Bearer {r.json()['schluessel']}"}
        assert (await anw.get("/v1/bildablage", headers=kopf)).status_code == 403          # nur ein Bildarchiv
        anfrage = {"prompt": "Ein Leuchtturm im Nebel", "model": "bildwerk-moss-image", "size": "512x512", "n": 1, "seed": 5}
        r = await anw.post("/v1/images/generations", headers=kopf, json=anfrage)
        assert r.status_code == 200
        r = await anw.post("/v1/images/generations", headers=archiv, json=anfrage | {"seed": 6})    # eigene Bilder des Archivs nicht
        assert r.status_code == 200
        liste = (await anw.get("/v1/bildablage", headers=archiv)).json()
        assert liste["wartend"] == 1 and liste["bilder"][0]["beschreibung"] == "Ein Leuchtturm im Nebel"
        e = liste["bilder"][0]
        assert (e["seed"], e["breite"], e["hoehe"], e["familie"]) == (5, 512, 512, "bildwerk-moss-image")
        bild = await anw.get(f"/v1/bildablage/{e['kennung']}", headers=archiv)
        assert bild.status_code == 200 and bild.content.startswith(b"\x89PNG") and bild.headers["content-type"] == "image/png"
        assert (await anw.delete(f"/v1/bildablage/{e['kennung']}", headers=archiv)).status_code == 204
        assert (await anw.get("/v1/bildablage", headers=archiv)).json()["wartend"] == 0
        assert (await anw.delete(f"/v1/bildablage/{e['kennung']}", headers=archiv)).status_code == 404
        # ältere Werkzeuge ändern ohne die Angabe: das Recht bleibt
        a = next(x for x in (await c.get("/api/lage")).json()["anwendungen"] if x["name"] == "Bildarchiv")
        daten = {k: a[k] for k in ("name", "prioritaet", "zonen", "extern_erlaubt", "gleichzeitig", "ketten", "docker_projekte", "faehigkeiten")}
        assert (await c.put(f"/api/anwendungen/{a['kennung']}", json=daten | {"gleichzeitig": 2})).status_code == 200
        assert next(x for x in (await c.get("/api/lage")).json()["anwendungen"] if x["name"] == "Bildarchiv")["bildarchiv"] is True



async def test_b15_bildvorlagen_nur_fuer_modelle_die_bearbeiten():
    """B15: Bildvorlagen (`images`) nimmt nur ein Modell, dessen Steckbrief Bearbeiten nennt, höchstens `vorlagen_max`; vor
    dem ersten Start (Steckbrief unbekannt) gehen sie in der Vorprüfung durch, nach dem Start entscheidet der Steckbrief.
    Der Ablauf schickt sie als Base64 an `v1/images/edits`, sonst dieselben Felder wie beim Erzeugen."""
    from schein.bilddienst import STECKBRIEF
    moss = _steckbrief()
    klein = Bildsteckbrief.model_validate({**STECKBRIEF, "modell": "flux2-klein", "name": "FLUX.2 klein 9B", "kann_bearbeiten": True,
                                           "vorlagen_max": 2, "lizenz_hinweis": "Nur nicht-kommerzielle Nutzung der Bilder."})
    assert regeln_pruefen(moss, None, 1, None, 1) == "MOSS-Image-SFT nimmt keine Bildvorlage an."
    assert regeln_pruefen(klein, None, 1, None, 2) is None
    assert regeln_pruefen(klein, None, 1, None, 3) == "Höchstens 2 Bildvorlagen je Anfrage, nicht 3."
    assert regeln_pruefen(None, None, 1, None, 1, vorab=True) is None
    assert regeln_pruefen(None, None, 1, None, 1) == "Dieses Bildmodell nimmt keine Bildvorlage an."
    assert "bis 2 Bildvorlagen" in klein.kurz() and klein.lizenz_hinweis
    # ein reines Bearbeitungsmodell (vorlagen_min) nimmt keine Anfrage ohne Vorlage an, auch nicht in der Vorprüfung
    edit = Bildsteckbrief.model_validate({**STECKBRIEF, "modell": "qwen-image-edit", "name": "Qwen-Image-Edit-2511", "kann_bearbeiten": True,
                                          "vorlagen_max": 3, "vorlagen_min": 1, "lizenz_hinweis": "Apache-2.0, frei nutzbar."})
    assert regeln_pruefen(edit, None, 1, None, 0) == "Qwen-Image-Edit-2511 rechnet nur mit Bildvorlage, mindestens 1."
    assert regeln_pruefen(edit, None, 1, None, 0, vorab=True) == "Qwen-Image-Edit-2511 rechnet nur mit Bildvorlage, mindestens 1."
    assert regeln_pruefen(edit, None, 1, None, 1) is None
    assert regeln_pruefen(edit, None, 1, None, 4) == "Höchstens 3 Bildvorlagen je Anfrage, nicht 4."
    assert "nur mit mindestens 1 Bildvorlage" in edit.kurz()
    vorlage = base64.b64encode(b"\x89PNGvorlage").decode()
    a = bildauftrag(BildAnfrage(prompt="Katze im Stil", images=[vorlage]), 5, klein)
    assert a.vorlagen == [b"\x89PNGvorlage"]
    with pytest.raises(Ablehnung) as e:
        bildauftrag(BildAnfrage(prompt="Katze im Stil", images=[vorlage]), 5, moss)
    assert e.value.grund == "eingabe"
    for falsch in (["kein base64!"], [vorlage] * 5):
        with pytest.raises(ValueError):
            BildAnfrage(prompt="Katze", images=falsch)
    app = schein_bilddienst(0.01, bearbeiten=True)
    async with laufend(app) as adresse:
        weg = OpenAIKompatibel(adresse)
        try:
            senden = lambda d: weg.durchleiten("", d)          # noqa: E731
            s = await ABLAUF.steckbrief(senden)
            assert s.kann_bearbeiten and s.vorlagen_max == 4 and s.lizenz_hinweis == "Nur nicht-kommerzielle Nutzung der Bilder."
            mit = await ABLAUF.erzeugen(senden, auftrag(vorlagen=[b"eins", b"zwei"], anzahl=1))
            ohne = await ABLAUF.erzeugen(senden, auftrag(anzahl=1))
        finally:
            await weg.schliessen()
    erste, zweite = app.state.lage.anfragen
    assert erste["pfad"] == "edits" and erste["vorlagen"] == [b"eins", b"zwei"] and erste["size"] == "1344x768"
    assert "pfad" not in zweite and len(mit.bilder) == len(ohne.bilder) == 1


async def test_b16_bild_bearbeiten_eigene_faehigkeit_ohne_bildablage(tmp_path):
    """B16 (ATL-6): `POST /v1/images/edits` ist die Fähigkeit bild_bearbeiten: Formular wie im OpenAI-Format (Datei im
    Feld image) oder JSON mit `images`, mindestens eine Vorlage, eigenes Recht. Das Modell hat die Fähigkeit, solange
    sein Steckbrief unbekannt ist oder Bearbeiten nennt. Die Ergebnisse gehen nicht in die Bildablage."""
    vorlage = b"\x89PNGvorlage"
    async with aufbau(tmp_path, startzeit_s=0.3, bearbeiten=True, faehigkeiten=("text", "bild_erzeugen", "bild_bearbeiten")) as (c, anw, kopf, dienst):
        r = await c.post("/api/anwendungen", json={"name": "Bildarchiv", "faehigkeiten": ["bild_erzeugen"], "bildarchiv": True})
        archiv = {"Authorization": f"Bearer {r.json()['schluessel']}"}
        felder = {"prompt": "Mach den Himmel blau", "model": "bildwerk-moss-image", "size": "512x512", "seed": "7", "stream": "true"}
        r = await anw.post("/v1/images/edits", headers=kopf, data=felder, files={"image": ("vorlage.png", vorlage, "image/png")})
        assert r.status_code == 200, r.text
        _, daten = _sse(r.text)
        strom = json.loads(daten[0])
        assert daten[-1] == "[DONE]" and base64.b64decode(strom["data"][0]["b64_json"]).startswith(b"\x89PNG")
        assert strom["x-leitstelle"]["seed"] == 7 and strom["x-leitstelle"]["groesse"] == "512x512"
        gesehen = (await dienst.get("/lage")).json()["anfragen"][-1]
        assert gesehen["pfad"] == "edits" and gesehen["prompt"] == "Mach den Himmel blau" and gesehen["vorlagen"] == [base64.b64encode(vorlage).decode()]
        # JSON mit images, ohne Strom; nach dem Start nennt der Steckbrief Bearbeiten, die Fähigkeit bleibt
        r = await anw.post("/v1/images/edits", headers=kopf, json={"prompt": "x", "model": "moss-image", "size": "512x512",
                                                                    "images": [base64.b64encode(vorlage).decode()]})
        assert r.status_code == 200, r.text
        liste = (await anw.get("/v1/steckbriefe", params={"faehigkeit": "bild_bearbeiten"}, headers=kopf)).json()["data"]
        assert [x["id"] for x in liste] == ["bildwerk-moss-image"]
        # ohne Vorlage, ohne Recht, ohne Modell
        r = await anw.post("/v1/images/edits", headers=kopf, data={"prompt": "x", "model": "moss-image"})
        assert r.status_code == 400 and "mindestens eine Bildvorlage" in r.json()["error"]["message"]
        r = await anw.post("/v1/images/edits", headers=archiv, data={"prompt": "x", "model": "moss-image"}, files={"image": ("v.png", vorlage, "image/png")})
        assert r.status_code == 403 and r.json()["error"]["code"] == "faehigkeit_nicht_erlaubt", r.text
        r = await anw.post("/v1/images/edits", headers=kopf, data={"prompt": "x"}, files={"image": ("v.png", vorlage, "image/png")})
        assert r.status_code == 400 and r.json()["error"]["code"] == "modell_fehlt" and r.json()["error"]["x-leitstelle"] == {"modelle": ["bildwerk-moss-image"]}
        # Bearbeitungen sind Zwischenstände der Anwendung: nichts wartet auf das Archiv
        assert (await anw.get("/v1/bildablage", headers=archiv)).json()["wartend"] == 0
