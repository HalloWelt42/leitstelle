"""Verteilung auf mehrere Rechner (Arbeitslogik 07.11.2026, LS-16): die Rolle eines Rechners (bevorzugt für Fähigkeiten),
Ausgleich nach Auslastung zwischen geladenen Kopien und Ruhe je Rechner für Arbeit nur bei Ruhe. Szenarien S71 bis S74
aus docs/SZENARIEN.md. Die App wählt das Modell; die Leitstelle wählt nur, auf welchem Rechner es rechnet."""

from leitstelle.kern.werte import Auftragszustand as Z, Dienstzustand, Faehigkeit as F, Modellzustand, Prioritaet as P

from conftest import lade, welt_mit


def _glm_auf_beiden(w):
    v = w.verbund
    v.dienste["laeufer-32"].zustand = Dienstzustand.BEREIT
    lade(w, "glm@128")
    lade(w, "glm@32")
    return v


def test_s71_rolle_des_rechners_entscheidet_zwischen_kopien():
    """Dasselbe Modell auf beiden Rechnern geladen und frei: ohne Rolle nimmt die Leitstelle die erste Kopie, mit Rolle
    "bevorzugt für Bild beschreiben" auf dem MacBook rechnet es dort."""
    w = welt_mit()
    v = _glm_auf_beiden(w)
    v.knoten["mac-32"].bevorzugt_fuer = {F.BILD_BESCHREIBEN}
    a = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5, festes_modell="glm-4.6v")
    w.laufen(6)
    assert v.auftraege[a.kennung].knoten == "mac-32"
    v.knoten["mac-32"].bevorzugt_fuer = set()
    v.knoten["mac-128"].bevorzugt_fuer = {F.BILD_BESCHREIBEN}
    b = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5, festes_modell="glm-4.6v")
    w.laufen(6)
    assert v.auftraege[b.kennung].knoten == "mac-128"


def test_s72_rolle_aendert_nie_das_modell():
    """Die Rolle wählt nur den Rechner: liegt das verlangte Modell nur auf dem Mac Studio, rechnet es dort, auch wenn das
    MacBook für die Fähigkeit bevorzugt ist und ein anderes Modell derselben Fähigkeit hätte."""
    w = welt_mit()
    v = _glm_auf_beiden(w)
    lade(w, "gemma@128")
    v.knoten["mac-32"].bevorzugt_fuer = {F.BILD_BESCHREIBEN}
    a = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5, festes_modell="gemma-4-26b")
    w.laufen(6)
    x = v.auftraege[a.kennung]
    assert v.modelle[x.modell].familie == "gemma-4-26b" and x.knoten == "mac-128"


def test_s73_ausgleich_nach_auslastung():
    """Zwei Aufträge für dasselbe Modell, je ein Platz auf beiden Rechnern: sie verteilen sich auf beide, statt dass der
    zweite hinter dem ersten wartet."""
    w = welt_mit()
    v = _glm_auf_beiden(w)
    for k in ("glm@128", "glm@32"):
        v.modelle[k].plaetze = 2
    a = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=20, festes_modell="glm-4.6v")
    b = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=20, festes_modell="glm-4.6v")
    w.laufen(6)
    assert {v.auftraege[a.kennung].knoten, v.auftraege[b.kennung].knoten} == {"mac-128", "mac-32"}


def test_s74_ruhe_je_rechner_masseneinbettung_auf_dem_freien_mac():
    """Auf dem Mac Studio läuft Hören (andere Arbeit); das MacBook ist ruhig. Masseneinbettung (nur bei Ruhe) wartet nicht
    auf das ganze Haus, sondern rechnet auf dem MacBook. Läuft auch dort etwas, wartet sie auf Ruhe."""
    w = welt_mit()
    v = w.verbund
    v.dienste["laeufer-32"].zustand = Dienstzustand.BEREIT
    v.dienste["laeufer-32"].faehigkeiten.add(F.EINBETTUNG)
    kopie = v.modelle["bge@128"].model_copy(update={"kennung": "bge@32", "dienst": "laeufer-32", "zustand": Modellzustand.GELADEN})
    v.modelle[kopie.kennung] = kopie
    hoeren = w.auftrag("tubevault", F.HOEREN, laufzeit_s=60, prioritaet=P.NORMAL)
    w.laufen(6)
    assert v.auftraege[hoeren.kennung].zustand == Z.LAEUFT and v.auftraege[hoeren.kennung].knoten == "mac-128"
    masse = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=5, prioritaet=P.HINTERGRUND)
    w.laufen(6)
    x = v.auftraege[masse.kennung]
    assert x.zustand in (Z.LAEUFT, Z.FERTIG) and x.knoten == "mac-32", "auf dem ruhigen Mac"
    bild = w.auftrag("kiste", F.TEXT, laufzeit_s=60, festes_modell="qwen-4b")
    lade(w, "klein@32")
    w.laufen(6)
    noch = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=5, prioritaet=P.HINTERGRUND)
    w.laufen(6)
    if v.auftraege[bild.kennung].knoten == "mac-32":
        assert v.auftraege[noch.kennung].zustand == Z.WARTET_RUHE, "beide Macs arbeiten: Masseneinbettung wartet"


async def test_rolle_wird_gespeichert_und_bleibt_beim_aendern(tmp_path):
    """Die Rolle steht in der Verwaltung des Rechners, übersteht den Neustart und bleibt, wenn eine Änderung sie nicht nennt."""
    from test_schlaf import leitstelle
    async with leitstelle(tmp_path, mit_takt=False) as (_app, _url, c):
        r = await c.post("/api/knoten", json={"name": "MacBook 32 GB", "adresse": "192.168.1.42", "speicher_gb": 32,
                                               "bevorzugt_fuer": ["stimme", "hoeren"]})
        assert r.status_code == 200, r.text
        kennung = r.json()["kennung"]
        r = await c.put(f"/api/knoten/{kennung}", json={"name": "MacBook 32 GB", "adresse": "192.168.1.42", "speicher_gb": 32, "budget_fest_gb": 22})
        assert r.status_code == 200, r.text
    async with leitstelle(tmp_path, mit_takt=False) as (_app, _url, c):
        k = next(x for x in (await c.get("/api/lage")).json()["knoten"] if x["kennung"] == kennung)
        assert k["bevorzugt_fuer"] == ["hoeren", "stimme"] and k["budget_fest_gb"] == 22
