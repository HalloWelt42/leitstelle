"""Regelwerk schaltbar und einstellbar (Auftrag 27.10.2026, Punkt 4): Maßnahmen an und aus, Regelwerte in ihren Grenzen,
gespeichert nur als Abweichung von der Vorgabe, beim Start geladen, jede Änderung mit alt und neu im Prüfprotokoll. Eine
Regel, die nicht mehr wirkt, nimmt ihren Zustand zurück. Szenarien V04 bis V08 in docs/SZENARIEN.md."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx

from leitstelle.api.app import erstellen
from leitstelle.kern.regelwerk import Einheit, Regelwerk, einstellbar, regelwert
from leitstelle.kern.werte import Automatik, Hintergrundstufe, Massnahmenart
from leitstelle.konfig import Konfig
from leitstelle.ports.ablage.datenbank import Datenbank
from leitstelle.ports.ablage.repositorien import Ablage

from schein.server import laufend


@asynccontextmanager
async def leitstelle(tmp_path):
    app = erstellen(Konfig(daten=tmp_path, oberflaeche=None), mit_takt=False)
    async with laufend(app) as url, httpx.AsyncClient(base_url=url, timeout=30) as c:
        yield app, c


async def _gespeichert(tmp_path) -> dict:
    db = Datenbank(tmp_path / "leitstelle.sqlite")
    await db.oeffnen()
    try:
        return await Ablage(db).einstellungen._lesen("regelwerk") or {}
    finally:
        await db.schliessen()


def test_jeder_wert_hat_bedeutung_und_grenzen_um_die_vorgabe():
    """Kein Regler ohne Wort, Erklärung und Einheit; die Vorgabe ab Werk liegt in den Grenzen für Änderungen von Hand."""
    vorgabe = Regelwerk()
    felder = set(Regelwerk.model_fields) - {"szenarien_an"}
    assert set(einstellbar()) == felder, "jeder Wert des Regelwerks ist beschrieben"
    for f in felder:
        rw = regelwert(f)
        assert rw.titel and rw.erklaerung.endswith(".") and rw.gruppe
        w = getattr(vorgabe, f)
        if rw.einheit in (Einheit.WAHL, Einheit.MEHRFACH):
            moeglich = {x for x, _ in rw.wahl}
            assert moeglich and all(x.value in moeglich for x in (w if isinstance(w, list) else [w])), f
        elif isinstance(w, (int, float)) and not isinstance(w, bool):
            assert rw.min is not None and rw.max is not None and rw.min <= w <= rw.max, f


async def test_v04_lesen_gruppen_mit_massnahmen_und_werten(tmp_path):
    async with leitstelle(tmp_path) as (_app, c):
        s = (await c.get("/api/regelwerk")).json()
        arten = [x["art"] for g in s["gruppen"] for x in g["szenarien"]]
        assert sorted(arten) == sorted(a.value for a in Massnahmenart), "jede Maßnahme genau einmal schaltbar"
        assert sorted(w["feld"] for g in s["gruppen"] for w in g["werte"]) == sorted(einstellbar())
        last = next(g for g in s["gruppen"] if g["gruppe"] == "last")
        assert last["titel"] == "Läufer und Last" and [x["art"] for x in last["szenarien"]] == ["laeufer_ohne_auftrag", "hintergrund_rechnerlast"]
        laeufer = last["szenarien"][0]
        assert laeufer["an"] is False and laeufer["vorgabe"] is False and laeufer["erklaerung"]
        frist = next(w for w in last["werte"] if w["feld"] == "laeufer_frist_s")
        assert frist["einheit"] == "sekunden" and frist["wert"] == 300 and frist["vorgabe"] == 300 and frist["min"] == 30
        automatik = next(w for g in s["gruppen"] for w in g["werte"] if w["feld"] == "automatik")
        assert automatik["wert"] == "selbst" and [x["wort"] for x in automatik["wahl"]] == ["Aus", "Vorschlagen", "Selbst handeln"]


async def test_v05_aendern_speichern_protokoll_und_neustart(tmp_path):
    async with leitstelle(tmp_path) as (app, c):
        r = await c.patch("/api/regelwerk", json={"szenarien_an": {"laeufer_ohne_auftrag": True}, "werte": {"laeufer_frist_s": 600, "speicher_warnschwelle": 0.9}})
        assert r.status_code == 200, r.text
        assert app.state.betrieb.verbund.regelwerk.laeufer_frist_s == 600, "wirkt sofort"
        lage = (await c.get("/api/lage")).json()["regelwerk"]
        assert lage["szenarien_an"]["laeufer_ohne_auftrag"] is True and lage["laeufer_frist_s"] == 600
        pruef = [(e["was"], e["gegenstand"]) for e in (await c.get("/api/pruefprotokoll")).json()["eintraege"]]
        assert ("Regelwert Frist (Läufer und Last): 5 min auf 10 min", "Regelwerk") in pruef
        assert ("Regelwert Speicher knapp ab (Speicher und Laden): 92 % auf 90 %", "Regelwerk") in pruef
        assert ("Regel Läufer ohne Auftrag: aus auf an", "Regelwerk") in pruef
        # zurück auf die Vorgabe: fällt aus den gespeicherten Abweichungen
        assert (await c.patch("/api/regelwerk", json={"werte": {"speicher_warnschwelle": 0.92}})).status_code == 200
    assert await _gespeichert(tmp_path) == {"laeufer_frist_s": 600.0, "szenarien_an": {"laeufer_ohne_auftrag": True}}, "nur Abweichungen"
    async with leitstelle(tmp_path) as (app, c):
        r = app.state.betrieb.verbund.regelwerk
        assert r.laeufer_frist_s == 600 and r.szenarien_an[Massnahmenart.LAEUFER_OHNE_AUFTRAG] and r.speicher_warnschwelle == 0.92, "beim Start geladen"


async def test_v06_grenzen_und_unbekanntes(tmp_path):
    async with leitstelle(tmp_path) as (app, c):
        for werte, grund, satz in [({"laeufer_frist_s": 5}, "eingabe", "Frist geht von 30 s bis 24 h, nicht 5 s."),
                                   ({"gibt_es_nicht": 1}, "unbekannt", "gibt_es_nicht"),
                                   ({"max_massnahmen_je_fenster": 2.5}, "eingabe", "ganze Zahl"),
                                   ({"geladene_zuerst": 1}, "eingabe", "an oder aus"),
                                   ({"automatik": "immer"}, "eingabe", "Selbst handeln"),
                                   ({"last_anhalten_ab_prozent": 40}, "eingabe", "liegt unter Fremdlast drosseln ab"),
                                   ({"docker_anhalten_ab_prozent": 60}, "eingabe", "liegt unter Docker-Last drosseln ab")]:
            r = await c.patch("/api/regelwerk", json={"werte": werte})
            assert r.status_code in (400, 404) and r.json()["grund"] == grund and satz in r.json()["begruendung"], r.text
        assert app.state.betrieb.verbund.regelwerk == Regelwerk(), "nichts übernommen"
        assert await _gespeichert(tmp_path) == {}


async def test_v07_abschalten_nimmt_den_zustand_der_regel_zurueck(tmp_path):
    """Eine gedrosselte Stufe bliebe sonst für immer: die Regel, die sie freigäbe, läuft nicht mehr. Ebenso Hintergrund bei
    Lage, wenn die Automatik nicht mehr selbst handelt."""
    async with leitstelle(tmp_path) as (app, c):
        k = (await c.post("/api/knoten", json={"name": "MacBook M4 Max 128 GB", "adresse": "127.0.0.1", "speicher_gb": 128})).json()["kennung"]
        b = app.state.betrieb
        b.hintergrund_stufe(k, Hintergrundstufe.GEDROSSELT, "Fremdlast im Mittel 62 %")
        b.hintergrund(False)
        r = await c.patch("/api/regelwerk", json={"szenarien_an": {"hintergrund_rechnerlast": False}})
        assert r.status_code == 200
        assert b.verbund.knoten[k].hintergrund_stufe == Hintergrundstufe.FREI and "wirkt nicht mehr" in b.verbund.knoten[k].hintergrund_grund
        assert not b.verbund.hintergrund_an, "Hintergrund bei Lage wirkt noch"
        await c.patch("/api/regelwerk", json={"werte": {"automatik": "vorschlagen"}})
        assert b.verbund.regelwerk.automatik == Automatik.VORSCHLAGEN and b.verbund.hintergrund_an
        meldungen = [m["text"] for m in (await c.get("/api/lage")).json()["meldungen"]]
        assert any("Hintergrund auf MacBook M4 Max 128 GB freigegeben" in m for m in meldungen)
        assert any(m.startswith("Hintergrund läuft wieder") for m in meldungen)
