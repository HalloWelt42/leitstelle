"""Schleifenschutz und Invarianten über lange Läufe mit 8 Anwendungen und 5 Anbindungen.
Szenarien S34 bis S40, S42 aus docs/SZENARIEN.md. Alles gemockt."""

import random

from leitstelle.kern.werte import Auftragszustand as Z, Dienstzustand, Faehigkeit as F, Massnahmenart as A, Modellzustand, Prioritaet as P, Zone

from conftest import ausgefuehrt, entlade, gesperrt, lade, welt_mit


def test_s34_flattern_wird_erkannt_und_gesperrt():
    """Ohne Verweildauer und Leerlaufgrenze würden zwei Bildmodelle auf dem MacBook ständig tauschen.
    Der Flatterschutz sperrt nach dem ersten Hin und Her."""
    # Schutzgrenze aus, damit beide Bildmodelle (GLM 9 Milliarden, Gemma 26 Milliarden) weichen dürfen
    w = welt_mit(mindestverweildauer_s=0, leerlauf_s=0, bedarfsfrist_s=0, schutzgrenze_mrd=0, fenster_s=600, ruhezeit_s=1800)
    v = w.verbund
    v.dienste["laeufer-32"].zustand = Dienstzustand.BEREIT
    v.knoten["mac-32"].budget_fest_gb = 18.0        # neben Whisper mittel (1,5) passt GLM (11,8) oder Gemma (16,2), nie beide
    v.knoten["mac-128"].budget_fest_gb = 4.0         # Mac Studio hilft nicht
    for m in v.modelle_auf("mac-128"):
        if not m.geschuetzt(v.regelwerk.schutzgrenze_mrd):
            entlade(w, m.kennung)
    v.anwendungen["kiste"].zonen = {Zone.HEIM}
    # abwechselnd: Kiste braucht GLM (11,8), Bildschmiede braucht Gemma (16,2 passt nicht neben GLM); je 5 s Arbeit
    for i in range(12):
        w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=4, zeit_s=10 + i * 40, festes_modell="glm-4.6v")
        w.auftrag("bildschmiede", F.BILD_BESCHREIBEN, laufzeit_s=4, zeit_s=30 + i * 40, festes_modell="gemma-4-26b", prioritaet=P.NORMAL)
    w.laufen(600)
    wechsel = w.wechsel_je_familie_knoten()
    assert gesperrt(w), "Flattern wurde erkannt und gemeldet"
    assert any("Flattern erkannt" in m.grund for m in gesperrt(w))
    assert all(n <= 3 for n in wechsel.values()), f"kein Dauerwechsel: {wechsel}"


def test_s35_mindestverweildauer_verhindert_hin_und_her():
    w = welt_mit(schutzgrenze_mrd=0)
    v = w.verbund
    v.dienste["laeufer-32"].zustand = Dienstzustand.BEREIT
    v.knoten["mac-32"].budget_fest_gb = 18.0
    v.knoten["mac-128"].budget_fest_gb = 4.0
    for m in v.modelle_auf("mac-128"):
        if not m.geschuetzt(v.regelwerk.schutzgrenze_mrd):
            entlade(w, m.kennung)
    for i in range(20):
        w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=4, zeit_s=10 + i * 60, festes_modell="glm-4.6v")
        w.auftrag("bildschmiede", F.BILD_BESCHREIBEN, laufzeit_s=4, zeit_s=40 + i * 60, festes_modell="gemma-4-26b", prioritaet=P.NORMAL)
    w.laufen(1200)
    wechsel = w.wechsel_je_familie_knoten()
    assert all(n <= 2 for n in wechsel.values()), f"höchstens ein Hin und Her je Modell in 20 Minuten: {wechsel}"


def test_s36_hoechstzahl_massnahmen_je_fenster():
    w = welt_mit(max_massnahmen_je_fenster=2, fenster_s=600)
    v = w.verbund
    v.dienste["laeufer-32"].zustand = Dienstzustand.BEREIT
    w.messwerk.merke_laufzeit("zusage", "text", 600.0)
    w.auftrag("zusage", F.TEXT, laufzeit_s=600)
    w.laufen(6)
    for i in range(6):
        w.auftrag("fundus", F.TEXT, laufzeit_s=5, zeit_s=10 + i * 5)   # jede würde extern ausweichen
    w.laufen(120)
    im_fenster = [m for m in ausgefuehrt(w) if m.zeit_s <= 600]
    assert len(im_fenster) <= 2
    assert any("Höchstzahl" in m.grund for m in gesperrt(w))


def test_s37_umleitung_hoechstens_einmal_je_auftrag():
    w = welt_mit()
    w.auftrag("zusage", F.TEXT, laufzeit_s=120)
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=200)
    w.laufen(30)
    assert w.verbund.auftraege[k.kennung].umgeleitet == 1
    # MacBook fällt aus: Umverteilen reiht neu ein; der Auftrag ist abgebrochen, wird aber nicht erneut umgeleitet
    w.verbund.knoten["mac-32"].erreichbar = False
    w.laufen(60)
    assert w.verbund.auftraege[k.kennung].umgeleitet == 1


def _zufallslauf(saat: int, dauer_s: int = 3600):
    rnd = random.Random(saat)
    w = welt_mit()
    v = w.verbund
    faehigkeiten = {
        "zusage": [F.TEXT, F.BILD_BESCHREIBEN], "tubevault": [F.HOEREN, F.STIMME, F.TEXT], "fundus": [F.TEXT, F.EINBETTUNG], "medienpool": [F.UEBERSETZEN],
        "kiste": [F.BILD_BESCHREIBEN, F.TEXT], "codehilfe": [F.TEXT], "rufzeichen": [F.TEXT, F.HOEREN, F.STIMME], "bildschmiede": [F.BILD_BESCHREIBEN, F.UEBERSETZEN],
    }
    zeit = 0.0
    while zeit < dauer_s * 0.8:
        zeit += rnd.expovariate(1 / 25)
        app = rnd.choice(list(faehigkeiten))
        f = rnd.choice(faehigkeiten[app])
        w.auftrag(app, f, laufzeit_s=rnd.choice([3, 5, 8, 15, 30, 60]), zeit_s=zeit)
    # Invarianten je Schritt prüfen
    geschuetzt_geladen: set[str] = {m.kennung for m in v.modelle.values() if m.im_speicher and m.geschuetzt(v.regelwerk.schutzgrenze_mrd) and not v.dienste[m.dienst].extern}
    for _ in range(dauer_s):
        w.schritt()
        for k in v.knoten.values():
            if k.erreichbar:
                assert v.geladen_gb(k.kennung) <= k.budget_gb(v.regelwerk.budget_reserve_gb) + 1e-6, f"Budget überschritten auf {k.name} bei {v.zeit_s}"
        for mk in geschuetzt_geladen:
            assert v.modelle[mk].zustand != Modellzustand.FREI, f"geschütztes Modell {mk} wurde entladen"
        for a in v.auftraege.values():
            if a.zustand == Z.LAEUFT and a.knoten:
                app = v.anwendungen[a.anwendung]
                assert v.knoten[a.knoten].zone in app.zonen, "Zone verletzt"
            if a.zustand == Z.LAEUFT and a.extern:
                assert v.anwendungen[a.anwendung].extern_erlaubt, "extern ohne Erlaubnis"
    return w


def test_s38_zufallslauf_invarianten_und_keine_verhungerung():
    for saat in (1, 2, 3):
        w = _zufallslauf(saat)
        w.laufen_bis_fertig(3600)
        v = w.verbund
        offen = [a for a in v.auftraege.values() if a.offen]
        assert not offen, f"Saat {saat}: {len(offen)} Aufträge verhungert, zum Beispiel {offen[0].kennung}: {offen[0].begruendung}"
        wechsel = w.wechsel_je_familie_knoten()
        assert all(n <= 8 for n in wechsel.values()), f"Saat {saat}: Dauerwechsel {wechsel}"


def test_s39_rechnende_modelle_werden_nie_entladen():
    """Der Schein-Verbund wirft eine Ausnahme, wenn jemand ein rechnendes Modell entlädt; der Zufallslauf oben darf das nie auslösen.
    Hier zusätzlich direkt: der Speicherplaner schlägt es nie vor."""
    from leitstelle.kern.messungen import Messwerk
    from leitstelle.kern.speicherplaner import planen
    w = welt_mit()
    w.auftrag("zusage", F.TEXT, laufzeit_s=100)
    w.laufen(6)
    plan = planen(w.verbund, "mac-128", 46.3, Messwerk(), familie="qwen-coder-next")
    assert "qwen80@128" not in plan.entladen


def test_s40_lage_beurteilung_zweige():
    from leitstelle.kern.lage import beurteilen
    from leitstelle.kern.werte import Lage
    w = welt_mit()
    entlade(w, "qwen80@128")
    assert beurteilen(w.verbund)[0] == Lage.RUHIG
    lade(w, "qwen80@128", vor_s=0.0)                 # gerade erst genutzt: darf innerhalb der Bedarfsfrist nicht weichen
    w.verbund.knoten["mac-32"].budget_fest_gb = 4.0
    w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5)
    w.laufen(6)
    assert beurteilen(w.verbund)[0] == Lage.ANGESPANNT
    w.auftrag("zusage", F.BILD_BESCHREIBEN, laufzeit_s=5, festes_modell="gemma-4-26b")
    w.laufen(6)
    assert beurteilen(w.verbund)[0] == Lage.ENGPASS


def test_s42_messungen_fliessen_in_entscheidungen():
    w = welt_mit()
    w.wahrheit.ladezeit["glm-4.6v@mac-32"] = 40.0     # wahre Ladezeit viel höher als die Schätzung (4,7 s)
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    w.laufen_bis_fertig(300)
    gemessen = w.messwerk.ladezeit("glm-4.6v", "mac-32", 11.8)
    assert gemessen.gemessen and 35 < gemessen.sekunden < 45
    # Zweiter Durchgang: mit der gemessenen Ladezeit lohnt Umleiten bei kurzer Wartezeit nicht mehr
    w.messwerk.merke_laufzeit("zusage", "text", 60.0)
    entlade(w, "glm@32")
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    w.laufen(6)
    w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    vorher = len(ausgefuehrt(w, A.UMLEITEN))
    w.laufen(30)
    assert len(ausgefuehrt(w, A.UMLEITEN)) == vorher, "Gewinn 54 s gegen Aufwand 40 s: Schwelle doppelt nicht erfüllt"
