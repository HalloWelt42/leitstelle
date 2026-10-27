"""Steckbrief je Modell (PROTOKOLL 4.8): von Hand vor Dienst vor abgeleitet, Messwerte aus dem Verlauf, Weg über die
Fassade nur für Modelle, die die Anwendung nutzen darf."""

from __future__ import annotations

from leitstelle.fach.steckbrief import Grenzen, messwerte_aus, zusammensetzen
from leitstelle.kern.modelle import Modell
from leitstelle.kern.werte import Auftragszustand, Eignung, Faehigkeit as F, Prioritaet, Zone
from leitstelle.ports.ablage.eintraege import AuftragEintrag, SteckbriefEintrag
from leitstelle.protokoll.knoten import Selbstauskunft
from leitstelle.protokoll.steckbrief import Messwerte, Quelle

from test_ende_zu_ende import _warte_bis, _zustand, aufbau


def _modell(parameter_mrd: float = 27) -> Modell:
    return Modell(kennung="m", name="Probe", dienst="d", familie="probe/modell", faehigkeiten={F.TEXT, F.UEBERSETZEN}, gb=10, parameter_mrd=parameter_mrd)


def test_von_hand_vor_dienst_vor_abgeleitet():
    dienst = Selbstauskunft(zweck="vom Dienst", eignung=[Eignung.DENKEN], quantisierung="4bit")
    s = zusammensetzen(_modell(), dienst, None, 262144, Zone.HEIM, Grenzen(), Messwerte())
    assert s.zweck == "vom Dienst" and s.eignung == [Eignung.DENKEN, Eignung.LANGE_TEXTE] and s.quantisierung == "4bit"
    assert s.herkunft["zweck"] == Quelle.DIENST and s.herkunft["kontext"] == Quelle.DIENST and "gemessen" not in s.herkunft
    assert s.parameter_aktiv_mrd == 27 and s.herkunft["parameter_aktiv_mrd"] == Quelle.ABGELEITET, "ohne A..B im Namen: dicht"
    hand = SteckbriefEintrag(familie="probe/modell", zweck="von Hand", eignung=[Eignung.SCHNELL], sprachen=["de"])
    s = zusammensetzen(_modell(), dienst, hand, 262144, Zone.EXTERN, Grenzen(anfragen_je_minute=10), Messwerte(auftraege=3))
    assert s.zweck == "von Hand" and s.eignung == [Eignung.SCHNELL], "von Hand ersetzt, nichts wird dazu abgeleitet"
    assert s.sprachen == ["de"] and s.herkunft["eignung"] == Quelle.HAND and s.zone == Zone.EXTERN and s.anfragen_je_minute == 10
    leer = zusammensetzen(_modell(parameter_mrd=0), Selbstauskunft(), None, 8192, Zone.HEIM, Grenzen(), Messwerte())
    assert leer.zweck == "" and leer.eignung == [] and leer.parameter_mrd is None and leer.herkunft == {"kontext": Quelle.DIENST}


def _auftrag(i: int, familie: str, dauer: float, token: int | None = None, erstes: float | None = None) -> AuftragEintrag:
    return AuftragEintrag(kennung=f"a{i}", anwendung="x", faehigkeit=F.TEXT, prioritaet=Prioritaet.NORMAL, zustand=Auftragszustand.FERTIG,
                          familie=familie, eingang_s=100.0 - i, start_s=100.0, ende_s=100.0 + dauer, token_aus=token, erstes_stueck_s=erstes)


def test_messwerte_aus_dem_verlauf():
    xs = [_auftrag(1, "a", 10, token=90, erstes=1), _auftrag(2, "a", 20, token=190, erstes=1), _auftrag(3, "a", 30), _auftrag(4, "b", 2),
          _auftrag(5, "c", 8, token=40, erstes=8)]          # ohne Strom: alles kam am Ende
    m = messwerte_aus(xs)
    assert m["a"].auftraege == 3 and m["a"].rechenzeit_s == 20 and m["a"].token_je_s == 10 and m["a"].erstes_stueck_s == 1
    assert m["b"].token_je_s is None and m["b"].rechenzeit_s == 2
    assert m["c"].token_je_s == 5, "ohne Strom gilt die ganze Rechenzeit"


async def test_e20_steckbrief_ueber_fassade_und_von_hand(tmp_path):
    async with aufbau(tmp_path) as (c, anw, lage, app):
        r = await anw.get("/models")
        x = {m["id"]: m["x-leitstelle"]["steckbrief"] for m in r.json()["data"]}
        s = x["qwen/qwen3-next-80b"]
        assert s["zweck"] == "Großes Textmodell für Übersetzen und lange Texte" and s["eignung"] == ["denken", "lange_texte"]
        assert s["quantisierung"] == "4bit" and s["kontext"] == 262144 and s["herkunft"]["zweck"] == "dienst"
        r = await anw.get("/steckbriefe", params={"eignung": "denken"})
        assert [m["id"] for m in r.json()["data"]] == ["qwen/qwen3-next-80b"]
        r = await anw.get("/steckbriefe", params={"faehigkeit": "einbettung"})
        assert [m["id"] for m in r.json()["data"]] == ["text-embedding-bge-m3"]

        r = await c.put("/api/steckbriefe", json={"familie": "qwen/qwen3-next-80b", "zweck": "Übersetzen ins Deutsche", "sprachen": ["de", "en"]})
        assert r.status_code == 200, r.text
        r = await anw.get("/steckbriefe", params={"sprache": "de"})
        erstes = r.json()["data"][0]
        assert erstes["id"] == "qwen/qwen3-next-80b", "wer die Sprache ausdrücklich kann, steht vorn"
        assert erstes["steckbrief"]["zweck"] == "Übersetzen ins Deutsche" and erstes["steckbrief"]["herkunft"]["zweck"] == "hand"
        assert erstes["steckbrief"]["eignung"] == ["denken", "lange_texte"], "Eignung von Hand leer: bleibt die des Dienstes"
        assert (await c.put("/api/steckbriefe", json={"familie": "gibt-es-nicht"})).status_code == 404
        await c.put("/api/steckbriefe", json={"familie": "qwen/qwen3-next-80b"})
        sicht = next(m for m in (await c.get("/api/lage")).json()["modelle"] if m["familie"] == "qwen/qwen3-next-80b")
        assert sicht["steckbrief"]["herkunft"]["zweck"] == "dienst", "ganz leer entfernt den Eintrag von Hand"

        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "messages": []})
        await _warte_bis(lambda: _zustand(c, r.headers["x-leitstelle-auftrag"], "fertig"))
        await app.state.betrieb._messwerte_holen()
        sicht = next(m for m in (await c.get("/api/lage")).json()["modelle"] if m["familie"] == "qwen/qwen3-next-80b")
        assert sicht["steckbrief"]["gemessen"]["auftraege"] == 1 and sicht["steckbrief"]["herkunft"]["gemessen"] == "gemessen"
