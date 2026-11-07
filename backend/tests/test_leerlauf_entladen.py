"""Entladen nach Leerlauf (Arbeitslogik 07.11.2026, LS-14): jedes Modell und jeder Dienst wird die Frist "Entladen nach"
(Vorgabe 60 s) nach dem letzten laufenden oder wartenden Auftrag entladen, auch kleine Modelle und die Einbettung; nur der
Schutz des Dienstes hält es. Szenarien S62 bis S67 aus docs/SZENARIEN.md."""

from leitstelle.kern.werte import Automatik, Faehigkeit as F, Massnahmenart as A, Massnahmenzustand as MZ, Modellzustand

from conftest import ausgefuehrt, welt_mit


def _genutzt(w, modell: str, vor_s: float = 0.0) -> None:
    """Modell geladen und vor `vor_s` zuletzt genutzt."""
    m = w.verbund.modelle[modell]
    m.zustand = Modellzustand.GELADEN
    m.geladen_seit_s = m.letzte_nutzung_s = w.verbund.zeit_s - vor_s


def test_s62_kleines_modell_und_einbettung_nach_der_frist_entladen():
    w = welt_mit(leerlauf_entladen=True)
    _genutzt(w, "bge@128")
    w.laufen(75)
    assert w.verbund.modelle["bge@128"].zustand == Modellzustand.FREI
    m = [x for x in ausgefuehrt(w, A.LEERLAUF_ENTLADEN) if x.modell == "bge-m3"]
    assert len(m) == 1 and "bge-m3 Einbettung auf Mac Studio entladen" in m[0].grund and "ohne Auftrag" in m[0].grund


def test_s63_vor_der_frist_bleibt_es():
    w = welt_mit(leerlauf_entladen=True)
    _genutzt(w, "bge@128")
    w.laufen(45)
    assert w.verbund.modelle["bge@128"].zustand == Modellzustand.GELADEN


def test_s64_wartender_auftrag_haelt_die_familie():
    """Ein Auftrag für bge-m3 wartet (Hintergrund am Hauptregler angehalten): das Modell bleibt, auch weit über die Frist."""
    from leitstelle.kern.werte import Auftragszustand as Z, Prioritaet as P
    w = welt_mit(leerlauf_entladen=True, ruhe_faehigkeiten=[])
    w.verbund.hintergrund_erlaubt = False
    _genutzt(w, "bge@128", vor_s=600)
    a = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=5, prioritaet=P.HINTERGRUND, festes_modell="bge-m3")
    w.laufen(90)
    assert w.verbund.auftraege[a.kennung].zustand == Z.EINGEREIHT
    assert w.verbund.modelle["bge@128"].zustand == Modellzustand.GELADEN


def test_s64b_frist_zaehlt_ab_dem_ende_des_letzten_auftrags():
    """Ein Auftrag rechnet 100 s auf bge-m3: solange bleibt es; entladen erst die Frist nach seinem Ende."""
    from leitstelle.kern.werte import Auftragszustand as Z
    w = welt_mit(leerlauf_entladen=True, ruhe_faehigkeiten=[])
    _genutzt(w, "bge@128")
    a = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=100, festes_modell="bge-m3")
    w.laufen(90)
    assert w.verbund.modelle["bge@128"].im_speicher
    w.laufen(50)
    assert w.verbund.auftraege[a.kennung].zustand == Z.FERTIG
    assert w.verbund.modelle["bge@128"].zustand == Modellzustand.GELADEN, "keine 60 s nach dem Ende"
    w.laufen(40)
    assert w.verbund.modelle["bge@128"].zustand == Modellzustand.FREI


def test_s65_schutz_des_dienstes_haelt_es():
    w = welt_mit(leerlauf_entladen=True)
    _genutzt(w, "bge@128", vor_s=600)
    w.verbund.modelle["bge@128"].schutz_vorgabe = True
    w.laufen(30)
    assert w.verbund.modelle["bge@128"].zustand == Modellzustand.GELADEN
    assert not [x for x in ausgefuehrt(w, A.LEERLAUF_ENTLADEN) if x.modell == "bge-m3"]


def test_s66_oft_gebraucht_ohne_flattersperre_und_ohne_hoechstzahl():
    """Dreimal im Fenster gebraucht und dreimal entladen: kein Flattern, keine Sperre, keine Höchstzahl; danach
    greifen Umschichtungen weiter (die Pflege verbraucht kein Kontingent)."""
    w = welt_mit(leerlauf_entladen=True, max_massnahmen_je_fenster=2)
    for _ in range(3):
        _genutzt(w, "bge@128")
        w.laufen(70)
        assert w.verbund.modelle["bge@128"].zustand == Modellzustand.FREI
    assert len([x for x in ausgefuehrt(w, A.LEERLAUF_ENTLADEN) if x.modell == "bge-m3"]) == 3
    assert not [m for m in w.verbund.massnahmen if m.zustand == MZ.GESPERRT and m.art == A.LEERLAUF_ENTLADEN]
    assert w.leitstelle.umschichter._im_fenster(w.verbund) == 0


def test_s67_vorschlagen_entlaedt_nichts():
    w = welt_mit(leerlauf_entladen=True, automatik=Automatik.VORSCHLAGEN)
    _genutzt(w, "bge@128")
    w.laufen(75)
    assert w.verbund.modelle["bge@128"].zustand == Modellzustand.GELADEN
    assert [m for m in w.verbund.massnahmen if m.art == A.LEERLAUF_ENTLADEN and m.zustand == MZ.GEPLANT]
