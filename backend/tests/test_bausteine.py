"""Bausteine einzeln: die Zweige, die im Zusammenspiel nur als Schutz dienen. Szenario S43 aus docs/SZENARIEN.md."""

from leitstelle.kern.messungen import Messwerk
from leitstelle.kern.regeln.bausteine import BAUSTEINE, Kontext, gewinn_gegen_aufwand
from leitstelle.simulation.standard import standard_verbund


def test_s43_gewinnschwelle_zweige():
    v = standard_verbund()
    k = Kontext(verbund=v, messwerk=Messwerk(), gewinn_s=5.0, aufwand_s=3.0)
    assert gewinn_gegen_aufwand(k, 2.0) is False, "5 s Gewinn gegen 3 s Aufwand: Schwelle 2 nicht erfüllt"
    assert k.werte["gewinn"] == "5 s" and k.werte["aufwand"] == "3 s" and k.werte["faktor"] == "2"
    k = Kontext(verbund=v, messwerk=Messwerk(), gewinn_s=6.0, aufwand_s=3.0)
    assert gewinn_gegen_aufwand(k, 2.0) is True
    k = Kontext(verbund=v, messwerk=Messwerk(), gewinn_s=0.0, aufwand_s=0.0)
    assert gewinn_gegen_aufwand(k, 1.0) is False, "ohne Gewinn nie (Kette: Aufwand null, Gewinn null)"
    k = Kontext(verbund=v, messwerk=Messwerk(), gewinn_s=4.0, aufwand_s=3.0)
    assert gewinn_gegen_aufwand(k) is False, "ohne Parameter gilt der Faktor des Regelwerks (2)"
    v.regelwerk.gewinnfaktor = 1.0
    assert gewinn_gegen_aufwand(k) is True


def test_s43b_jeder_baustein_hat_wort_und_erklaerung():
    """Die Palette im Regelwerk-Editor liest Wort und Erklärung; nichts darf leer sein, kein Schlüssel wird gedruckt."""
    assert len(BAUSTEINE) >= 30
    for name, b in BAUSTEINE.items():
        assert b.art in ("ausloeser", "pruefung", "aktion"), name
        assert b.wort and b.wort != name, name
        assert b.erklaerung and len(b.erklaerung) > 15, name
