"""Wie die App einen Auftrag einordnet: Einzel oder Masse (LS-24) und wichtig (LS-23). Szenarien S92 bis S98 aus
docs/SZENARIEN.md; die Regeln stehen für Apps in docs/ARBEITSLOGIK.md."""

from __future__ import annotations

from leitstelle.kern.werte import Auftragsart as Art, Auftragszustand as Z, Dienstzustand, Faehigkeit as F, Prioritaet as P
from leitstelle.kern.zuteiler import reihenfolge, vorrang_gesperrt

from conftest import lade, welt_mit
from test_schlaf import MODELL, _warte_bis, aufbau


def test_s92_einzel_vor_masse_ueber_alle_faehigkeiten():
    """Eine Masse-Vertonung (Sprache, Rang 1) kommt nach einer einzelnen Suche (Einbettung, Rang 7); innerhalb von Einzel
    gilt weiter die Rangfolge."""
    w = welt_mit(ruhe_faehigkeiten=[])
    buch = w.auftrag("rufzeichen", F.STIMME, art=Art.MASSE)
    suche = w.auftrag("fundus", F.EINBETTUNG)
    text = w.auftrag("zusage", F.TEXT)
    assert [a.kennung for a in reihenfolge(w.verbund)] == [text.kennung, suche.kennung, buch.kennung]


def test_s93_masse_nur_bei_ruhe_je_mac():
    """Masse von einer App ohne Fähigkeitsregel (Text): auf dem Mac Studio läuft Einzelarbeit, das MacBook ist durch den
    Akku gesperrt: die Masse wartet auf Ruhe (nicht auf den Akku). Ist das MacBook wieder frei, rechnet sie dort, ohne
    dass der Mac Studio etwas abgibt."""
    w = welt_mit(ruhe_faehigkeiten=[])
    v = w.verbund
    v.dienste["laeufer-32"].zustand = Dienstzustand.BEREIT
    v.akku_melden("mac-32", 20)
    einzel = w.auftrag("zusage", F.TEXT, laufzeit_s=120)
    w.laufen(6)
    assert v.auftraege[einzel.kennung].knoten == "mac-128"
    masse = w.auftrag("kiste", F.TEXT, laufzeit_s=5, festes_modell="qwen-4b", art=Art.MASSE)
    w.laufen(6)
    x = v.auftraege[masse.kennung]
    assert x.zustand == Z.WARTET_RUHE and "Akku" not in (x.begruendung or ""), x.begruendung
    v.akku_melden("mac-32", 75)
    w.laufen(60)
    x = v.auftraege[masse.kennung]
    assert x.zustand == Z.FERTIG and x.knoten == "mac-32", "auf dem ruhigen MacBook"
    assert v.auftraege[einzel.kennung].zustand == Z.LAEUFT, "der Mac Studio rechnet ungestört weiter"


def test_s94_wichtig_geht_allem_vor_auch_sprache():
    w = welt_mit()
    stimme = w.auftrag("rufzeichen", F.STIMME, prioritaet=P.DRINGEND)
    text = w.auftrag("zusage", F.TEXT)
    bild = w.auftrag("kiste", F.BILD_BESCHREIBEN, wichtig=True)
    spaeter = w.auftrag("fundus", F.TEXT, wichtig=True)
    assert [a.kennung for a in reihenfolge(w.verbund)] == [bild.kennung, spaeter.kennung, stimme.kennung, text.kennung]
    assert not w.verbund.nur_bei_ruhe(w.auftrag("fundus", F.EINBETTUNG, prioritaet=P.HINTERGRUND, wichtig=True))


def test_s95_wichtig_haelt_seinen_rechner_frei():
    """Das 80B rechnet für Zusage; ein wichtiger Auftrag für das 80B wartet. Laufendes rechnet zu Ende, aber auf dem Mac
    Studio startet nichts Neues (die Einbettung wartet mit Grund); danach ist der wichtige Auftrag dran."""
    w = welt_mit(ruhe_faehigkeiten=[])
    v = w.verbund
    lauf = w.auftrag("zusage", F.TEXT, laufzeit_s=30)
    w.laufen(6)
    assert v.auftraege[lauf.kennung].zustand == Z.LAEUFT
    wichtig = w.auftrag("kiste", F.TEXT, laufzeit_s=5, festes_modell="qwen-next-80b", wichtig=True)
    such = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=5)
    w.laufen(6)
    assert v.auftraege[wichtig.kennung].zustand == Z.EINGEREIHT
    s = v.auftraege[such.kennung]
    assert s.zustand == Z.EINGEREIHT and "für einen wichtigen Auftrag von Kiste freigehalten" in (s.begruendung or "")
    w.laufen(40)
    assert v.auftraege[lauf.kennung].zustand == Z.FERTIG and v.auftraege[wichtig.kennung].zustand == Z.FERTIG
    assert v.auftraege[such.kennung].zustand == Z.FERTIG
    assert v.auftraege[such.kennung].start_s >= v.auftraege[wichtig.kennung].start_s, "erst der wichtige, dann die Suche"


def test_s96_zwei_wichtige_wer_zuerst_kam():
    """Zwei wichtige Aufträge für denselben Mac: der zweite wartet und erfährt, wer den Rechner hält."""
    w = welt_mit(ruhe_faehigkeiten=[])
    v = w.verbund
    lauf = w.auftrag("zusage", F.TEXT, laufzeit_s=30)
    w.laufen(6)
    erster = w.auftrag("kiste", F.TEXT, laufzeit_s=5, festes_modell="qwen-next-80b", wichtig=True)
    w.laufen(2)
    zweiter = w.auftrag("codehilfe", F.TEXT, laufzeit_s=5, festes_modell="qwen-next-80b", wichtig=True)
    w.laufen(4)
    assert "von Kiste" in (v.auftraege[zweiter.kennung].begruendung or "")
    w.laufen(60)
    a, b = v.auftraege[erster.kennung], v.auftraege[zweiter.kennung]
    assert v.auftraege[lauf.kennung].zustand == a.zustand == b.zustand == Z.FERTIG and a.start_s < b.start_s


def test_s97_wichtig_ist_nicht_durch_den_vorrang_der_sprache_gesperrt():
    w = welt_mit()
    v = w.verbund
    stimme = w.auftrag("rufzeichen", F.STIMME, laufzeit_s=30)
    w.laufen(6)
    assert v.auftraege[stimme.kennung].knoten == "mac-128"
    normal = w.auftrag("zusage", F.TEXT, laufzeit_s=5)
    wichtig = w.auftrag("kiste", F.TEXT, laufzeit_s=5, festes_modell="qwen-next-80b", wichtig=True)
    m = v.modelle["qwen80@128"]
    assert vorrang_gesperrt(v, v.auftraege[normal.kennung], m) is not None
    assert vorrang_gesperrt(v, v.auftraege[wichtig.kennung], m) is None


async def test_s98_koepfe_der_fassade(tmp_path):
    """X-Leitstelle-Art: masse und X-Leitstelle-Wichtig: ja kommen am Auftrag an; Unbekanntes zählt wie keine Angabe."""
    async with aufbau(tmp_path) as a:
        for koepfe, art, wichtig in (({"X-Leitstelle-Art": "masse"}, "masse", False), ({"X-Leitstelle-Wichtig": "ja"}, "einzel", True),
                                     ({"X-Leitstelle-Art": "irgendwas", "X-Leitstelle-Wichtig": "vielleicht"}, "einzel", False)):
            r = await a.anw.post("/v1/chat/completions", json={"model": MODELL, "messages": [{"role": "user", "content": "Hallo"}]}, headers=koepfe)
            assert r.status_code == 200, r.text
            kennung = r.headers["x-leitstelle-auftrag"]
            auftrag = a.app.state.betrieb.verbund.auftraege.get(kennung)
            if auftrag is not None:
                assert auftrag.art.value == art and auftrag.wichtig is wichtig
            eintrag = (await a.c.get(f"/api/auftraege/{kennung}")).json()
            texte = " ".join(s["text"] for s in eintrag["schritte"])
            assert ("Massenaufgabe" in texte) == (art == "masse") and ("als wichtig markiert" in texte) == wichtig


async def test_s100_einschaetzung_vor_dem_senden(tmp_path):
    """POST /v1/einschaetzung spielt den Auftrag durch, ohne ihn einzureihen: frei heißt sofort; ohne Modell die Ablehnung
    mit Grundwort; ein offener wichtiger Auftrag steht in der Liste."""
    async with aufbau(tmp_path) as a:
        vorher = len(a.app.state.betrieb.verbund.auftraege)
        r = await a.anw.post("/v1/einschaetzung", json={"model": MODELL})
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["sofort"] is True and e["rechner"] == "Mac Studio" and e["wichtige"] == [] and e["abgelehnt"] is None
        assert (await a.anw.post("/v1/einschaetzung", json={})).json()["abgelehnt"] == "modell_fehlt"
        assert len(a.app.state.betrieb.verbund.auftraege) == vorher, "nichts eingereiht"
        a.laeufer.stueck_pause_s, a.laeufer.stuecke = 0.2, 30
        import asyncio
        lauf = asyncio.create_task(a.anw.post("/v1/chat/completions", json={"model": MODELL, "stream": True, "messages": [{"role": "user", "content": "x"}]},
                                              headers={"X-Leitstelle-Wichtig": "ja"}))

        async def laeuft():
            return any(x.wichtig for x in a.app.state.betrieb.verbund.offene_auftraege())
        await _warte_bis(laeuft)
        e = (await a.anw.post("/v1/einschaetzung", json={"model": MODELL, "art": "masse"})).json()
        assert e["wichtige"] and e["wichtige"][0]["anwendung"] == "Transkription"
        await lauf
        assert (await a.anw.post("/v1/einschaetzung", json={"model": MODELL}, headers={"Authorization": "Bearer falsch"})).status_code == 401
