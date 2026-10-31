"""Arbeit nur bei Ruhe (HELF-89, Nutzer 31.10.2026: "Einbettungen sind nicht so privilegiert, die können auch laufen, wenn
nichts los ist"). Szenarien S54 bis S61 aus docs/SZENARIEN.md in der Schein-Welt, E21 und V08 auf echten Ports.

Masseneinbettung (Fähigkeit in `ruhe_faehigkeiten`, Priorität bis `ruhe_bis_prioritaet`) bekommt nur ein Modell, wenn keine
andere Arbeit läuft oder wartet und die letzte seit `ruhe_ab_s` vorbei ist; sonst wartet sie im Zustand `wartet_ruhe`.
Ein laufender Stapel rechnet zu Ende, die übrigen warten. Suchen einer App (Priorität normal) bleiben unberührt."""

from __future__ import annotations

import asyncio

import httpx

from leitstelle.kern.modelle import Regelwerk
from leitstelle.kern.werte import Auftragszustand as Z, Faehigkeit as F, Lage, Massnahmenzustand, Prioritaet as P

from conftest import welt_mit
from test_ende_zu_ende import _warte_bis, aufbau
from test_regelwerk import _gespeichert, leitstelle

TAKT = 5        # die Schein-Welt teilt im Takt der Regeln zu


def _masse(w, laufzeit_s: float = 5.0):
    """Ein Stapel der Masseneinbettung, wie Fundus ihn schickt (Priorität Hintergrund)."""
    return w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=laufzeit_s, prioritaet=P.HINTERGRUND)


def _hoeren(w, laufzeit_s: float = 30.0):
    """Andere Arbeit: ein Hörlauf (TubeVault hört im Hintergrund, aber Hören ist keine Arbeit nur bei Ruhe)."""
    return w.auftrag("tubevault", F.HOEREN, laufzeit_s=laufzeit_s)


def test_s54_ohne_andere_arbeit_rechnet_die_einbettung_sofort():
    w = welt_mit()
    e = _masse(w)
    w.laufen(TAKT + 1)
    assert e.zustand in (Z.LAEUFT, Z.FERTIG) and e.start_s <= TAKT + 1, "zugeteilt im ersten Takt, gestartet im Schritt danach"


def test_s55_wartet_waehrend_andere_arbeit_laeuft_und_danach_die_ruhezeit():
    w = welt_mit()
    h = _hoeren(w, 30)
    e = _masse(w)
    w.laufen(10)
    assert h.zustand == Z.LAEUFT
    assert e.zustand == Z.WARTET_RUHE
    assert e.begruendung.startswith("wartet auf Ruhe") and "TubeVault" in e.begruendung
    w.laufen(h.laufzeit_s)                       # Hören ist fertig, die Ruhezeit läuft
    assert h.zustand == Z.FERTIG and e.zustand == Z.WARTET_RUHE
    assert "Ruhe gilt nach 60 s" in e.begruendung and e.voraussichtlich_s is not None
    w.laufen_bis_fertig(400)
    assert e.zustand == Z.FERTIG
    assert h.ende_s + 60 <= e.start_s <= h.ende_s + 60 + TAKT, "erst nach der Ruhezeit, dann aber gleich"


def test_s56_gibt_nach_der_laufende_stapel_rechnet_zu_ende_die_uebrigen_warten():
    w = welt_mit()
    e1 = _masse(w, 20)
    w.laufen(TAKT + 1)
    assert e1.zustand == Z.LAEUFT
    h = _hoeren(w, 40)
    e2 = _masse(w)
    w.laufen(25)
    assert e1.zustand == Z.FERTIG and e1.fortschritt_s >= e1.laufzeit_s, "nicht abgebrochen, zu Ende gerechnet"
    assert h.zustand == Z.LAEUFT and e2.zustand == Z.WARTET_RUHE
    w.laufen_bis_fertig(500)
    assert e2.zustand == Z.FERTIG and e2.start_s >= h.ende_s + 60


def test_s57_suchen_einer_app_warten_nicht():
    """Eine Suche bettet die Frage mit Priorität normal ein: sie läuft auch, während andere Arbeit läuft, und vor der
    Masseneinbettung."""
    w = welt_mit()
    h = _hoeren(w, 60)
    masse = _masse(w)
    suche = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=2, prioritaet=P.NORMAL)
    w.laufen(15)
    assert suche.zustand == Z.FERTIG and h.zustand == Z.LAEUFT
    assert masse.zustand == Z.WARTET_RUHE


def test_s58_alles_einstellbar():
    # Ruhe ab 0 s: gleich nach dem Ende der anderen Arbeit
    w = welt_mit(ruhe_ab_s=0)
    h, e = _hoeren(w, 20), _masse(w)
    w.laufen_bis_fertig(300)
    assert h.ende_s <= e.start_s <= h.ende_s + TAKT
    # keine Fähigkeit nur bei Ruhe: wie vor HELF-89, die Einbettung rechnet neben dem Hören
    w = welt_mit(ruhe_faehigkeiten=[])
    h, e = _hoeren(w, 60), _masse(w)
    w.laufen(15)
    assert e.zustand == Z.FERTIG and h.zustand == Z.LAEUFT
    # bis Priorität normal: auch die Suche wartet
    w = welt_mit(ruhe_bis_prioritaet=P.NORMAL)
    h = _hoeren(w, 60)
    suche = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=2, prioritaet=P.NORMAL)
    w.laufen(15)
    assert suche.zustand == Z.WARTET_RUHE
    # eine andere Fähigkeit nur bei Ruhe: Hintergrundtext wartet auf das Hören
    w = welt_mit(ruhe_faehigkeiten=[F.TEXT])
    h = _hoeren(w, 60)
    text = w.auftrag("tubevault", F.TEXT, laufzeit_s=5)
    e = _masse(w)
    w.laufen(15)
    assert text.zustand == Z.WARTET_RUHE and e.zustand == Z.FERTIG


def test_s59_die_fairness_frist_hebt_arbeit_nur_bei_ruhe_nicht_an():
    """Hintergrund rückt nach der Frist auf normal; Arbeit nur bei Ruhe nicht, sie darf Tage warten."""
    w = welt_mit(hintergrund_spaetestens_s=60)
    h = _hoeren(w, 400)
    e = _masse(w)
    w.laufen(300)
    assert h.zustand == Z.LAEUFT and e.zustand == Z.WARTET_RUHE


def test_s60_warten_auf_ruhe_loest_keine_massnahme_aus_und_haelt_keine_instanz():
    """Kein Andrang (keine weiteren Einbettungsinstanzen), kein Vorwärmen, keine angespannte Lage; eine weitere Instanz
    weicht nach der Ruhe der Einbettung, obwohl Stapel auf Ruhe warten."""
    w = welt_mit(einbettung_andrang_s=1, einbettung_ruhe_s=30)
    v = w.verbund
    v.dienste["laeufer-128"].einbettung_instanzen = 3
    v.modelle["bge@128"].instanzen_hoechstens = 3
    w.instanz_starten("laeufer-128", "bge-m3", "bge@128")
    zusatz = next(k for k, m in v.modelle.items() if m.zusatz)
    h = _hoeren(w, 200)
    stapel = [_masse(w) for _ in range(6)]
    w.laufen(120)
    assert all(e.zustand == Z.WARTET_RUHE for e in stapel)
    assert not [m for m in v.massnahmen if m.art.value == "einbettung_verstaerken" and m.zustand == Massnahmenzustand.AUSGEFUEHRT]
    assert w.leitstelle.lage == Lage.RUHIG
    assert v.modelle[zusatz].zustand.value == "frei", "die weitere Instanz ist zurückgebaut"
    assert h.zustand == Z.LAEUFT


def test_s61_wartende_andere_arbeit_zaehlt_wie_laufende():
    """Wartet andere Arbeit (hier auf einen belegten Platz), ist es nicht ruhig."""
    w = welt_mit()
    a1 = w.auftrag("zusage", F.TEXT, laufzeit_s=40)
    a2 = w.auftrag("zusage", F.TEXT, laufzeit_s=10)
    e = _masse(w)
    w.laufen(10)
    assert a2.zustand == Z.EINGEREIHT and e.zustand == Z.WARTET_RUHE
    w.laufen_bis_fertig(400)
    assert e.start_s >= a2.ende_s + 60


async def test_e21_einbettung_wartet_ueber_http_auf_ruhe_und_wird_fertig(tmp_path):
    """Echte Ports: ein Text strömt, die Masseneinbettung (Kopf X-Leitstelle-Prioritaet: hintergrund) wartet im Zustand
    wartet_ruhe, ihre Anfrage bleibt offen (kein Fehler, keine Zeitüberschreitung) und kommt nach Text und Ruhezeit mit
    Vektoren zurück. Eine Suche (normal) kommt sofort."""
    async with aufbau(tmp_path, regelwerk=Regelwerk(ruhe_ab_s=1.0)) as (c, anw, lage, app):
        lage.stuecke, lage.stueck_pause_s = 60, 0.05          # etwa 3 s Text
        b = app.state.betrieb

        async def text():
            r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "stream": True, "messages": []})
            assert r.status_code == 200
            return asyncio.get_running_loop().time()

        strom = asyncio.create_task(text())
        await _warte_bis(lambda: _laeuft_text(b))
        masse = asyncio.create_task(anw.post("/embeddings", json={"model": "text-embedding-bge-m3", "input": ["Abschnitt"]},
                                             headers={"X-Leitstelle-Prioritaet": "hintergrund"}))
        await _warte_bis(lambda: _zustand_einbettung(c, "wartet_ruhe"))
        sicht = next(a for a in (await c.get("/api/lage")).json()["auftraege"] if a["faehigkeit"] == "einbettung")
        assert sicht["begruendung"].startswith("wartet auf Ruhe")
        suche = await anw.post("/embeddings", json={"model": "text-embedding-bge-m3", "input": ["Frage"]},
                               headers={"X-Leitstelle-Prioritaet": "normal"})
        assert suche.status_code == 200 and not masse.done(), "die Suche wartet nicht, die Masse schon"
        ende_text = await strom
        r = await asyncio.wait_for(masse, 30)
        fertig = asyncio.get_running_loop().time()
        assert r.status_code == 200 and len(r.json()["data"]) == 1
        assert fertig - ende_text >= 1.0, "erst nach der Ruhezeit"


async def _laeuft_text(b) -> bool:
    return any(a.faehigkeit == F.TEXT and a.zustand == Z.LAEUFT for a in b.verbund.auftraege.values())


async def _zustand_einbettung(c: httpx.AsyncClient, zustand: str) -> bool:
    return any(a["faehigkeit"] == "einbettung" and a["zustand"] == zustand for a in (await c.get("/api/lage")).json()["auftraege"])


async def test_v08_nur_bei_ruhe_in_der_oberflaeche_einstellbar(tmp_path):
    """Die drei Werte stehen in der Gruppe "Nur bei Ruhe" mit ihren Möglichkeiten, lassen sich ändern (Prüfprotokoll mit
    Worten) und werden geprüft."""
    async with leitstelle(tmp_path) as (app, c):
        s = (await c.get("/api/regelwerk")).json()
        ruhe = next(g for g in s["gruppen"] if g["gruppe"] == "ruhe")
        werte = {w["feld"]: w for w in ruhe["werte"]}
        assert ruhe["titel"] == "Nur bei Ruhe" and set(werte) == {"ruhe_faehigkeiten", "ruhe_bis_prioritaet", "ruhe_ab_s"}
        assert werte["ruhe_faehigkeiten"]["einheit"] == "mehrfach" and werte["ruhe_faehigkeiten"]["vorgabe"] == ["einbettung"]
        assert {"wert": "hoeren", "wort": "Hören"} in werte["ruhe_faehigkeiten"]["wahl"]
        assert werte["ruhe_bis_prioritaet"]["vorgabe"] == 0 and werte["ruhe_bis_prioritaet"]["wahl"][0] == {"wert": 0, "wort": "Hintergrund"}
        assert werte["ruhe_ab_s"]["vorgabe"] == 60

        r = await c.patch("/api/regelwerk", json={"werte": {"ruhe_faehigkeiten": ["text", "einbettung", "text"], "ruhe_bis_prioritaet": 1,
                                                              "ruhe_ab_s": 120}})
        assert r.status_code == 200, r.text
        regel = app.state.betrieb.verbund.regelwerk
        assert regel.ruhe_faehigkeiten == [F.TEXT, F.EINBETTUNG] and regel.ruhe_bis_prioritaet == P.NORMAL and regel.ruhe_ab_s == 120
        assert await _gespeichert(tmp_path) == {"ruhe_faehigkeiten": ["text", "einbettung"], "ruhe_bis_prioritaet": 1, "ruhe_ab_s": 120.0}
        protokoll = [e["was"] for e in (await c.get("/api/pruefprotokoll")).json()["eintraege"]]
        assert "Regelwert Fähigkeiten nur bei Ruhe (Nur bei Ruhe): Einbettung auf Text, Einbettung" in protokoll
        assert "Regelwert Nur bei Ruhe bis Priorität (Nur bei Ruhe): Hintergrund auf Normal" in protokoll

        for werte_, satz in [({"ruhe_faehigkeiten": ["fliegen"]}, "Auswahl aus"), ({"ruhe_faehigkeiten": "einbettung"}, "Auswahl aus"),
                             ({"ruhe_bis_prioritaet": 7}, "Hintergrund, Normal"), ({"ruhe_bis_prioritaet": True}, "Hintergrund, Normal"),
                             ({"ruhe_ab_s": -1}, "Ruhe ab geht von")]:
            r = await c.patch("/api/regelwerk", json={"werte": werte_})
            assert r.status_code == 400 and satz in r.json()["begruendung"], r.text
        r = await c.patch("/api/regelwerk", json={"werte": {"ruhe_faehigkeiten": []}})
        assert r.status_code == 200 and app.state.betrieb.verbund.regelwerk.ruhe_faehigkeiten == []
