"""Prüffenster für die Abnahme im Betrieb (LS-20): nur die Anwendung der Abnahme bekommt neue Arbeit, Sprachausgabe läuft
weiter, alles andere wartet mit Grund; Frist, Probewert des Akkus. Szenarien S86 bis S91 aus docs/SZENARIEN.md."""

from __future__ import annotations

import pytest

from leitstelle.kern.werte import Auftragszustand as Z, Faehigkeit as F, Massnahmenart as A

from conftest import ausgefuehrt, welt_mit
from test_schlaf import aufbau


def test_s86_nur_die_abnahme_bekommt_neue_arbeit():
    """Fenster für Kiste: der Textauftrag von Fundus wartet mit Grund, Kiste rechnet, Sprachausgabe läuft trotzdem; was vor
    dem Fenster lief, rechnet zu Ende."""
    w = welt_mit()
    v = w.verbund
    vorher = w.auftrag("zusage", F.TEXT, laufzeit_s=30)
    w.laufen(5)
    assert v.auftraege[vorher.kennung].zustand in (Z.LAEUFT, Z.ZUGETEILT)
    v.pruefung_oeffnen("kiste", 600, "Abnahme LS-20")
    live = w.auftrag("fundus", F.TEXT, laufzeit_s=5)
    probe = w.auftrag("kiste", F.TEXT, laufzeit_s=5, festes_modell="qwen-4b")
    stimme = w.auftrag("rufzeichen", F.STIMME, laufzeit_s=5)
    w.laufen(60)
    assert v.auftraege[vorher.kennung].zustand == Z.FERTIG, "Laufendes rechnet zu Ende"
    a = v.auftraege[live.kennung]
    assert a.zustand == Z.EINGEREIHT and "Abnahme im Betrieb" in (a.begruendung or "") and "Abnahme LS-20" in a.begruendung
    assert v.auftraege[probe.kennung].zustand == Z.FERTIG
    assert v.auftraege[stimme.kennung].zustand == Z.FERTIG, "Sprachausgabe hat Durchlass"


def test_s87_frist_schliesst_das_fenster_von_selbst():
    w = welt_mit()
    v = w.verbund
    v.pruefung_oeffnen("kiste", 120)
    live = w.auftrag("zusage", F.TEXT, laufzeit_s=5)
    w.laufen(100)
    assert v.auftraege[live.kennung].zustand == Z.EINGEREIHT
    w.laufen(60)
    assert v.prueffenster is None and v.auftraege[live.kennung].zustand == Z.FERTIG


def test_s88_probewert_akku_und_zurueck_zum_messwert():
    """Messwert 50 %: frei. Probewert 20 % sperrt, 75 % gibt frei, 20 % sperrt wieder; beim Schließen gilt der Messwert mit
    der Sperre von vorher (frei), auch wenn 50 % unter "wieder Arbeit ab" liegt."""
    w = welt_mit()
    v = w.verbund
    v.akku_melden("mac-32", 50)
    with pytest.raises(ValueError, match="nur im offenen Prüffenster"):
        v.pruefung_akku("mac-32", 20)
    v.pruefung_oeffnen("kiste", 600)
    assert v.pruefung_akku("mac-32", 20) is True and v.knoten["mac-32"].akku_prozent == 20
    assert v.akku_melden("mac-32", 49) is None and v.knoten["mac-32"].akku_gesperrt, "der Messwert ändert nichts am Probewert"
    assert v.pruefung_akku("mac-32", 75) is False
    assert v.pruefung_akku("mac-32", 20) is True
    assert v.pruefung_schliessen() == {"mac-32": False}
    k = v.knoten["mac-32"]
    assert k.akku_prozent == 49 and not k.akku_gesperrt and v.akku_probewert("mac-32") is None


def test_s89_grenzen_des_fensters():
    w = welt_mit()
    v = w.verbund
    with pytest.raises(ValueError, match="höchstens 1800"):
        v.pruefung_oeffnen("kiste", 1801)
    with pytest.raises(ValueError, match="gibt es nicht"):
        v.pruefung_oeffnen("unbekannt", 60)
    v.pruefung_oeffnen("kiste", 60)
    with pytest.raises(ValueError, match="schon ein Prüffenster"):
        v.pruefung_oeffnen("zusage", 60)


def test_s90_gehaltene_live_arbeit_loest_keine_massnahme_aus():
    """Der Fall aus S07 (Bild wartet, das MacBook hätte Platz), aber im Prüffenster einer anderen Anwendung: die Leitstelle
    leitet den gehaltenen Auftrag nicht um und startet keinen Dienst dafür."""
    w = welt_mit()
    v = w.verbund
    v.pruefung_oeffnen("rufzeichen", 600)
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    w.laufen(60)
    assert not ausgefuehrt(w, A.UMLEITEN)


async def test_s91_schnittstelle_lagebild_und_auskunft(tmp_path):
    """Öffnen, Probewert, Anzeige im Lagebild und in /v1/lage, Schließen über die Verwaltung."""
    async with aufbau(tmp_path) as a:
        lage = (await a.c.get("/api/lage")).json()
        app = lage["anwendungen"][0]["kennung"]
        knoten = lage["knoten"][0]["kennung"]
        r = await a.c.put("/api/pruefung/akku", json={"knoten": knoten, "prozent": 20})
        assert r.status_code == 409, "ohne Fenster kein Probewert"
        r = await a.c.post("/api/pruefung", json={"anwendung": app, "dauer_s": 600, "grund": "Abnahme"})
        assert r.status_code == 200, r.text
        assert (await a.c.post("/api/pruefung", json={"anwendung": app, "dauer_s": 600})).status_code == 409
        assert (await a.c.put("/api/pruefung/akku", json={"knoten": knoten, "prozent": 20})).status_code == 200
        lage = (await a.c.get("/api/lage")).json()
        assert lage["pruefung"]["anwendung_kennung"] == app and lage["pruefung"]["akku_probe"] == {knoten: 20}
        k = next(x for x in lage["knoten"] if x["kennung"] == knoten)
        assert k["akku_probe"] == 20 and k["akku_gesperrt"] is True
        auskunft = (await a.anw.get("/v1/lage")).json()
        assert auskunft["pruefung"]["durchlass"] == ["stimme"]
        assert any(x["akku_probe"] for x in auskunft["rechner"])
        texte = [m["text"] for m in lage["meldungen"]]
        assert any("Prüffenster offen" in t for t in texte) and any("(Probewert der Prüfung)" in t for t in texte)
        assert (await a.c.delete("/api/pruefung")).status_code == 200
        lage = (await a.c.get("/api/lage")).json()
        assert lage["pruefung"] is None
        k = next(x for x in lage["knoten"] if x["kennung"] == knoten)
        assert k["akku_probe"] is None and k["akku_gesperrt"] is False
        assert (await a.c.delete("/api/pruefung")).status_code == 409
