"""Was der echte Betrieb vom Kern braucht: Ladesperre nach abgelehntem Laden, begrenzte Verläufe im Dauerlauf.
Szenarien S44 und S45 aus docs/SZENARIEN.md."""

from leitstelle.kern.werte import Auftragszustand as Z, Faehigkeit as F, Modellzustand

from conftest import entlade, welt_mit


def test_s44_ladesperre_verhindert_sofortigen_neuversuch():
    """Der Läufer hat das Laden von GLM abgelehnt. Bis die Sperre abläuft, plant niemand einen neuen Versuch:
    der Auftrag wartet mit dem Grund im Wortlaut, danach wird geladen."""
    w = welt_mit()
    v = w.verbund
    entlade(w, "qwen80@128")
    v.knoten["mac-32"].budget_fest_gb = 4.0
    glm = v.modelle["glm@128"]
    glm.ladesperre_bis_s = v.zeit_s + 30
    glm.ladesperre_grund = "zu wenig Speicher"
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5, festes_modell="glm-4.6v")
    w.laufen(10)
    a = v.auftraege[k.kennung]
    assert a.zustand == Z.WARTET_SPEICHER
    assert "abgelehnt (zu wenig Speicher)" in a.begruendung
    assert glm.zustand == Modellzustand.FREI and not w.ladevorgaenge
    w.laufen_bis_fertig(120)
    assert a.zustand == Z.FERTIG and a.modell == "glm@128" and a.start_s >= 30


def test_s45_verlaeufe_bleiben_im_dauerlauf_begrenzt():
    """Zwei Stunden mit Aufträgen und Maßnahmen: der Umschichter behält nur, was Fenster und Sperren brauchen."""
    w = welt_mit()
    for i in range(240):
        w.auftrag("zusage", F.TEXT, laufzeit_s=8, zeit_s=10 + i * 30)
        w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=4, zeit_s=20 + i * 30)
    w.laufen(7200)
    u = w.leitstelle.umschichter
    fenster = w.verbund.regelwerk.fenster_s
    assert all(w.verbund.zeit_s - m.zeit_s <= fenster for m in u.verlauf)
    assert all(w.verbund.zeit_s - z <= fenster for z, _ in u.bewegungen)
    assert all(bis > w.verbund.zeit_s for bis in u.sperren.values())
    assert len(u.verlauf) <= w.verbund.regelwerk.max_massnahmen_je_fenster + 50
