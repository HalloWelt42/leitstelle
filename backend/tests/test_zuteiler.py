"""Zuteiler: Direktweg, Plätze, Priorität, Fairness, Laden, Warten auf Speicher, Rechte, Kontingent, Hauptregler.
Szenarien S01 bis S08 und S28 aus docs/SZENARIEN.md."""

from leitstelle.kern.werte import Auftragszustand as Z, Betriebsmodus, Faehigkeit as F, Prioritaet as P, Zone

from leitstelle.kern.zuteiler import reihenfolge, zuteilen
from leitstelle.kern.messungen import Messwerk

from conftest import entlade, lade, welt_mit


def test_s01_direktweg_geladen_und_frei(welt):
    a = welt.auftrag("zusage", F.TEXT, laufzeit_s=10)
    welt.laufen(6)
    assert welt.verbund.auftraege[a.kennung].zustand == Z.LAEUFT
    assert welt.verbund.auftraege[a.kennung].modell == "qwen80@128"
    assert "Direktweg" in welt.verbund.auftraege[a.kennung].begruendung
    assert not welt.ladevorgaenge, "nichts wird geladen, das Modell war schon da"


def test_s02_platz_belegt_zweiter_wartet_und_folgt(welt):
    a1 = welt.auftrag("zusage", F.TEXT, laufzeit_s=30)
    a2 = welt.auftrag("zusage", F.TEXT, laufzeit_s=10)
    welt.laufen(10)
    v = welt.verbund
    assert v.auftraege[a1.kennung].zustand == Z.LAEUFT
    assert v.auftraege[a2.kennung].zustand == Z.EINGEREIHT
    assert "belegt" in v.auftraege[a2.kennung].begruendung
    welt.laufen_bis_fertig(200)
    assert v.auftraege[a2.kennung].zustand == Z.FERTIG
    assert v.auftraege[a2.kennung].start_s >= v.auftraege[a1.kennung].ende_s


def test_s03_prioritaet_hoch_vor_hintergrund(welt):
    blocker = welt.auftrag("fundus", F.TEXT, laufzeit_s=30)
    welt.laufen(6)
    hinten = welt.auftrag("tubevault", F.TEXT, laufzeit_s=5)
    vorn = welt.auftrag("zusage", F.TEXT, laufzeit_s=5)
    welt.laufen_bis_fertig(300)
    v = welt.verbund
    assert v.auftraege[vorn.kennung].start_s < v.auftraege[hinten.kennung].start_s


def test_s04_fairness_hintergrund_rueckt_auf():
    w = welt_mit(hintergrund_spaetestens_s=20)
    blocker = w.auftrag("fundus", F.TEXT, laufzeit_s=40)
    w.laufen(6)
    hinten = w.auftrag("tubevault", F.TEXT, laufzeit_s=5)
    w.laufen(30)  # Hintergrund wartet jetzt länger als die Frist
    spaeter = w.auftrag("zusage", F.TEXT, laufzeit_s=5, prioritaet=P.NORMAL)
    w.laufen_bis_fertig(300)
    v = w.verbund
    assert v.auftraege[hinten.kennung].start_s <= v.auftraege[spaeter.kennung].start_s


def test_s05_laden_ohne_entladen_wenn_platz(welt):
    entlade(welt, "qwen80@128")
    a = welt.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5)
    welt.laufen(5)
    v = welt.verbund
    assert v.auftraege[a.kennung].zustand == Z.ZUGETEILT
    assert v.auftraege[a.kennung].modell == "glm@128"
    assert v.modelle["glm@128"].zustand.value in ("laedt", "geladen")
    welt.laufen_bis_fertig(120)
    assert v.auftraege[a.kennung].zustand == Z.FERTIG
    assert "glm-4.6v@mac-128" in welt.messwerk.ladezeiten, "die Ladezeit wurde gemessen"


def test_s06_wartet_auf_speicher_mit_begruendung():
    w = welt_mit()
    w.verbund.knoten["mac-32"].budget_fest_gb = 4.0   # MacBook kann nicht helfen
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    a = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5)
    w.laufen(10)
    k = w.verbund.auftraege[a.kennung]
    assert k.zustand == Z.WARTET_SPEICHER
    assert "passen nicht" in k.begruendung
    assert k.wartet_auf_knoten == "mac-128"


def test_s07_rechte_zone_und_faehigkeit(welt):
    # Kiste darf nicht extern; Fundus darf. Fähigkeit außerhalb der Anwendung wird abgelehnt.
    a = welt.auftrag("kiste", F.HOEREN, laufzeit_s=5)
    welt.laufen(5)
    assert welt.verbund.auftraege[a.kennung].zustand == Z.ABGELEHNT
    b = welt.auftrag("zusage", F.TEXT, laufzeit_s=5, festes_modell="qwen-35b-extern")
    welt.laufen(5)
    assert welt.verbund.auftraege[b.kennung].zustand == Z.ABGELEHNT, "Zusage darf nicht extern"


def test_s08_kontingent_gleichzeitig():
    w = welt_mit()
    w.verbund.anwendungen["fundus"].gleichzeitig = 1
    w.verbund.dienste["laeufer-128"].plaetze = 3
    a1 = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=30)
    a2 = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=5)
    w.laufen(10)
    v = w.verbund
    assert v.auftraege[a1.kennung].zustand == Z.LAEUFT
    assert v.auftraege[a2.kennung].zustand == Z.EINGEREIHT
    assert "Kontingent" in v.auftraege[a2.kennung].begruendung


def test_s28_hauptregler_auslaufen_und_halt(welt):
    a1 = welt.auftrag("zusage", F.TEXT, laufzeit_s=30)
    welt.laufen(6)
    welt.verbund.betriebsmodus = Betriebsmodus.AUSLAUFEN
    a2 = welt.auftrag("zusage", F.TEXT, laufzeit_s=5)
    welt.laufen(40)
    v = welt.verbund
    assert v.auftraege[a1.kennung].zustand == Z.FERTIG, "Laufendes endet normal"
    assert v.auftraege[a2.kennung].zustand == Z.EINGEREIHT and "Hauptregler" in v.auftraege[a2.kennung].begruendung
    welt.verbund.betriebsmodus = Betriebsmodus.HALT
    welt.laufen(20)
    assert all(m.zustand.value != "ausgefuehrt" for m in v.massnahmen if m.zeit_s > 40), "bei Halt keine Maßnahmen"
    welt.verbund.betriebsmodus = Betriebsmodus.NORMAL
    welt.laufen_bis_fertig(120)
    assert v.auftraege[a2.kennung].zustand == Z.FERTIG


def test_s46_ablehnung_mit_grundwort_und_extern_auf_wunsch(welt):
    """Ablehnungen tragen das Wort für die Fassade. Eine Anwendung, die extern darf und ein externes Modell
    ausdrücklich verlangt, bekommt es; ohne Erlaubnis wird sie mit Zonengrund abgelehnt."""
    v = welt.verbund
    f = welt.auftrag("fundus", F.TEXT, laufzeit_s=5, festes_modell="qwen-35b-extern")
    z = welt.auftrag("zusage", F.TEXT, laufzeit_s=5, festes_modell="qwen-35b-extern")
    u = welt.auftrag("kiste", F.TEXT, laufzeit_s=5, festes_modell="gibt-es-nicht")
    h = welt.auftrag("kiste", F.HOEREN, laufzeit_s=5)
    welt.laufen(5)
    assert v.auftraege[f.kennung].zustand in (Z.ZUGETEILT, Z.LAEUFT) and v.auftraege[f.kennung].extern
    assert v.auftraege[z.kennung].grund == "zone_nicht_erlaubt"
    assert v.auftraege[u.kennung].grund == "kein_modell"
    assert v.auftraege[h.kennung].grund == "faehigkeit_nicht_erlaubt"
    v.dienste["laeufer-128"].zustand = v.dienste["laeufer-128"].zustand.__class__.NICHT_ERREICHBAR
    k = welt.auftrag("kiste", F.TEXT, laufzeit_s=5)
    welt.laufen(5)
    assert v.auftraege[k.kennung].grund == "dienst_nicht_erreichbar"


def test_s47_hauptregler_hintergrund_haelt_ohne_ausnahme():
    """Der Schalter am Hauptregler hält Hintergrund absolut an, auch über die Fairness-Frist hinaus;
    die Regel Hintergrund bei Lage schaltet ihn nicht wieder ein."""
    w = welt_mit(hintergrund_spaetestens_s=20)
    w.verbund.hintergrund_erlaubt = False
    t = w.auftrag("tubevault", F.TEXT, laufzeit_s=5)
    w.laufen(60)
    a = w.verbund.auftraege[t.kennung]
    assert a.zustand == Z.EINGEREIHT and "Hauptregler" in a.begruendung
    w.verbund.hintergrund_erlaubt = True
    w.laufen_bis_fertig(60)
    assert a.zustand == Z.FERTIG


def test_plaetze_je_modell_maschinenraum_bestimmt_eintrag_begrenzt(welt):
    """Plätze je Modell: beim Maschinenraum (Dienst art agent) gilt, was seine Dienstdatei meldet; sonst begrenzt der
    Eintrag des Dienstes, was das Modell meldet. Ohne Meldung gilt der Eintrag."""
    v = welt.verbund
    m = v.modelle["qwen80@128"]
    d = v.dienste[m.dienst]
    d.plaetze, m.plaetze = 1, None
    assert v.plaetze(m) == 1
    m.plaetze = 4
    assert v.plaetze(m) == 1, "der Eintrag des Modell-Läufers begrenzt"
    d.plaetze = 8
    assert v.plaetze(m) == 4
    d.art = "agent"
    d.plaetze = 1
    assert v.plaetze(m) == 4, "beim Maschinenraum zählt die Dienstdatei"
    m.plaetze = None
    assert v.plaetze(m) == 1


def test_einbettung_zuerst(welt):
    """Nutzer 18.10.2026: Einbettung hat höchste Priorität, vor jedem Text, auch einem dringenden; untereinander gilt
    wieder die Priorität."""
    text = welt.auftrag("zusage", F.TEXT, prioritaet=P.DRINGEND)
    spaet = welt.auftrag("fundus", F.EINBETTUNG, prioritaet=P.HINTERGRUND)
    such = welt.auftrag("fundus", F.EINBETTUNG, prioritaet=P.NORMAL)
    assert [a.kennung for a in reihenfolge(welt.verbund)] == [such.kennung, spaet.kennung, text.kennung]


def test_grenze_je_minute_des_externen_anbieters(welt):
    """Hetzner nimmt etwa 10 Anfragen je Minute an; die Leitstelle schickt nie mehr. Gesendete Anfragen im Fenster
    und Zuteilungen desselben Laufs zählen; wer darüber liegt, wartet mit Frist und Grund."""
    v = welt.verbund
    d = v.dienste["extern-anbieter"]
    d.anfragen_je_minute = 3
    v.anfrage_gesendet("extern-anbieter", v.zeit_s - 50)     # fällt in 10 s aus dem Fenster
    v.anfrage_gesendet("extern-anbieter", v.zeit_s - 70)     # schon draußen
    auftraege = [welt.auftrag("fundus", F.TEXT, festes_modell="qwen-35b-extern") for _ in range(3)]
    e = zuteilen(v, Messwerk())
    assert [z.auftrag for z in e.zuteilungen] == [a.kennung for a in auftraege[:2]]
    w = next(x for x in e.wartend if x.auftrag == auftraege[2].kennung)
    assert "Grenze von 3 Anfragen je Minute erreicht" in w.begruendung and w.voraussichtlich_s == 10.0
    d.gesperrt_bis_s = v.zeit_s + 30                           # nach 429 des Anbieters
    assert v.anfrage_frei_in_s("extern-anbieter") == 30.0
