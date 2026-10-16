"""Speicherplaner: passt, entlädt nur so viel wie nötig, schützt, wartet. Szenarien S12 bis S15, S35."""

import pytest

from leitstelle.kern.messungen import Messwerk
from leitstelle.kern.speicherplaner import planen
from leitstelle.kern.werte import Faehigkeit as F

from conftest import entlade, lade


def test_passt_ohne_entladen(welt):
    entlade(welt, "qwen80@128")
    plan = planen(welt.verbund, "mac-128", 11.8, Messwerk(), familie="glm-4.6v")
    assert plan.passt and not plan.entladen
    assert "passen" in plan.begruendung


def test_entlaedt_nur_so_viel_wie_noetig_groesste_zuerst(welt):
    lade(welt, "gemma@128")       # 16,2 GB ungenutzt
    lade(welt, "glm@128")         # 11,8 GB ungenutzt
    # geladen: 84,7 + 1,1 + 3,1 + 1,9 + 16,2 + 11,8 = 118,8 > Budget 96: schon überbucht, Plan für 46,3 (Coder)
    plan = planen(welt.verbund, "mac-128", 46.3, Messwerk(), familie="qwen-coder-next")
    assert plan.passt
    assert plan.entladen[0] == "qwen80@128", "größtes ungenutztes Modell zuerst"
    assert "qwen80@128" in plan.entladen


def test_s13_geschuetzte_und_zugeteilte_bleiben(welt):
    welt.verbund.modelle["qwen80@128"].parameter_mrd = 8   # unter der Schutzgrenze
    plan = planen(welt.verbund, "mac-128", 11.8, Messwerk(), familie="glm-4.6v")
    assert not plan.passt
    assert "geschützt" in plan.begruendung
    assert "bge-m3" in plan.begruendung


def test_s14_mindestverweildauer_haelt(welt):
    welt.verbund.modelle["qwen80@128"].geladen_seit_s = welt.verbund.zeit_s - 10
    plan = planen(welt.verbund, "mac-128", 11.8, Messwerk(), familie="glm-4.6v")
    assert not plan.passt
    assert "Mindestverweildauer" in plan.begruendung


def test_s15_rechnendes_modell_mit_frei_nach(welt):
    welt.auftrag("zusage", F.TEXT, laufzeit_s=50)
    welt.laufen(6)
    plan = planen(welt.verbund, "mac-128", 11.8, Messwerk(), familie="glm-4.6v")
    assert not plan.passt
    assert plan.frei_nach_s is not None and plan.frei_nach_s > 0
    assert "qwen80@128" in plan.blockiert_durch


def test_leerlauf_nur_wenn_lange_ungenutzt(welt):
    welt.verbund.modelle["qwen80@128"].letzte_nutzung_s = welt.verbund.zeit_s - 60
    plan = planen(welt.verbund, "mac-128", 11.8, Messwerk(), familie="glm-4.6v", nur_leerlauf=True)
    assert not plan.passt
    plan = planen(welt.verbund, "mac-128", 11.8, Messwerk(), familie="glm-4.6v", nur_leerlauf=True, leerlauf_grenze_s=30)
    assert plan.passt, "mit kürzerer Frist (Bedarf) darf es weichen"
    welt.verbund.modelle["qwen80@128"].letzte_nutzung_s = welt.verbund.zeit_s - 5000
    plan = planen(welt.verbund, "mac-128", 11.8, Messwerk(), familie="glm-4.6v", nur_leerlauf=True)
    assert plan.passt and plan.entladen == ["qwen80@128"]


def test_s48_schutzvorgabe_des_dienstes_geht_der_regel_vor(welt):
    """Ein Dienst ohne Parameterzahl (Maschinenraum) wäre nach der Regel geschützt; erlaubt sein Dienst das Anhalten,
    darf er weichen. Verbietet er es, bleibt auch ein großes Modell stehen."""
    m = welt.verbund.modelle["qwen80@128"]
    schutz = welt.verbund.regelwerk.schutzgrenze_mrd
    m.parameter_mrd = 0
    assert m.geschuetzt(schutz)
    m.schutz_vorgabe = False
    assert not m.geschuetzt(schutz)
    plan = planen(welt.verbund, "mac-128", 11.8, Messwerk(), familie="glm-4.6v")
    assert plan.passt and "qwen80@128" in plan.entladen
    m.parameter_mrd, m.schutz_vorgabe = 80, True
    assert m.geschuetzt(schutz)


def test_s49_verplant_wird_der_bedarf_belegt_ist_der_ist_wert(welt):
    """Ein Dienst, der seine Modelle erst bei Bedarf lädt: verplant wird sein Bedarf, nicht der kleine Ist-Wert."""
    m = welt.verbund.modelle["qwen80@128"]
    vorher_geplant, vorher_belegt = welt.verbund.geladen_gb("mac-128"), welt.verbund.belegt_bekannt_gb("mac-128")
    m.gb_jetzt = 0.5
    assert welt.verbund.geladen_gb("mac-128") == vorher_geplant
    assert welt.verbund.belegt_bekannt_gb("mac-128") == pytest.approx(vorher_belegt - m.gb + 0.5)
