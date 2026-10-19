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



def test_folgeaufruf_an_dieselbe_instanz(welt):
    """X-Leitstelle-Instanz: ein Folgeaufruf (Ergebnis abholen) geht nur an die genannte Instanz, auch wenn eine andere
    frei ist; läuft sie nicht mehr, lehnt die Leitstelle mit "instanz_weg" ab."""
    v = welt.verbund
    grund = v.modelle["whisperm@32"]
    zweite = grund.model_copy(update={"kennung": "whisper-mittel.2@hoerer-32", "zusatz": True})
    v.modelle[zweite.kennung] = zweite
    a = welt.auftrag("rufzeichen", F.HOEREN, festes_modell="whisper-mittel")
    a.feste_instanz = zweite.kennung
    e = zuteilen(v, Messwerk())
    assert [(z.auftrag, z.modell) for z in e.zuteilungen] == [(a.kennung, zweite.kennung)]
    weg = welt.auftrag("rufzeichen", F.HOEREN, festes_modell="whisper-mittel")
    weg.feste_instanz = "whisper-mittel.3@hoerer-32"
    e = zuteilen(v, Messwerk())
    assert [(x.auftrag, x.grund) for x in e.abgelehnt] == [(weg.kennung, "instanz_weg")]


def _einschlafen(v, knoten: str) -> None:
    """Wie die Leitstelle nach `knoten.schlaeft`: Rechner schläft, seine Dienste auch."""
    from leitstelle.kern.werte import Dienstzustand
    k = v.knoten[knoten]
    k.schlaeft_seit_s, k.erreichbar = v.zeit_s, False
    for d in v.dienste_auf(knoten):
        d.zustand = Dienstzustand.SCHLAEFT


def test_s50_rechner_schlaeft_ablehnung_nennt_ihn(welt):
    """Liegt das Modell nur auf einem schlafenden Rechner, lautet die Ablehnung rechner_schlaeft mit dem Rechner; die Lage
    bleibt ruhig und nennt ihn als Hinweis."""
    from leitstelle.kern.lage import beurteilen
    from leitstelle.kern.werte import Knotenzustand, Lage
    v = welt.verbund
    _einschlafen(v, "mac-128")
    a = welt.auftrag("tubevault", F.STIMME, laufzeit_s=5)
    e = zuteilen(v, Messwerk())
    [w] = e.abgelehnt
    assert (w.auftrag, w.grund, w.schlafende_knoten) == (a.kennung, "rechner_schlaeft", ["mac-128"])
    assert w.begruendung == "Mac Studio schläft; der Auftrag kann erst laufen, wenn er wach ist."
    assert v.knoten["mac-128"].zustand == Knotenzustand.SCHLAEFT
    lage, grund = beurteilen(v)
    assert lage == Lage.RUHIG and grund.endswith("Mac Studio schläft") and "nicht erreichbar" not in grund


def test_s51_unangekuendigt_weg_ist_nicht_erreichbar_statt_zone(welt):
    """Fehler vom 19.10.2026: ein Rechner, der ohne Abmeldung verschwand, gab 403 zone_nicht_erlaubt (endgültig); jetzt
    dienst_nicht_erreichbar (die App wartet). Eine Zone, die wirklich nicht passt, bleibt 403."""
    from leitstelle.kern.werte import Dienstzustand
    v = welt.verbund
    v.knoten["mac-128"].erreichbar = False
    for d in v.dienste_auf("mac-128"):
        d.zustand = Dienstzustand.NICHT_ERREICHBAR
    a = welt.auftrag("tubevault", F.STIMME, laufzeit_s=5)
    z = welt.auftrag("zusage", F.TEXT, laufzeit_s=5, festes_modell="qwen-35b-extern")
    e = {w.auftrag: w for w in zuteilen(v, Messwerk()).abgelehnt}
    assert e[a.kennung].grund == "dienst_nicht_erreichbar" and not e[a.kennung].schlafende_knoten
    assert e[z.kennung].grund == "zone_nicht_erlaubt"
    v.anwendungen["tubevault"].zonen = {Zone.FERN}             # Mac Studio liegt im Heimnetz: die Zone passt wirklich nicht
    b = welt.auftrag("tubevault", F.STIMME, laufzeit_s=5)
    e = {w.auftrag: w for w in zuteilen(v, Messwerk()).abgelehnt}
    assert e[b.kennung].grund == "zone_nicht_erlaubt"


def test_s52_schlaf_nur_wenn_alle_passenden_rechner_schlafen(welt):
    """Gibt es die Familie auch auf einem wachen Rechner, rechnet der; ist der nur weg (nicht schlafend), heißt es
    dienst_nicht_erreichbar, damit die App nicht ohne Grenze wartet."""
    from leitstelle.kern.werte import Dienstzustand
    v = welt.verbund
    _einschlafen(v, "mac-128")
    a = welt.auftrag("rufzeichen", F.HOEREN, laufzeit_s=5)          # whisper-mittel auf dem MacBook, whisper-gross auf Mac Studio
    e = zuteilen(v, Messwerk())
    assert [(z.auftrag, z.knoten) for z in e.zuteilungen] == [(a.kennung, "mac-32")]
    v.dienste["hoerer-32"].zustand = Dienstzustand.NICHT_ERREICHBAR
    v.knoten["mac-32"].erreichbar = False
    del v.auftraege[a.kennung]
    b = welt.auftrag("rufzeichen", F.HOEREN, laufzeit_s=5)
    [w] = zuteilen(v, Messwerk()).abgelehnt
    assert (w.auftrag, w.grund) == (b.kennung, "dienst_nicht_erreichbar")
    _einschlafen(v, "mac-32")
    [w] = zuteilen(v, Messwerk()).abgelehnt
    assert (w.grund, w.schlafende_knoten) == ("rechner_schlaeft", ["mac-128", "mac-32"])
    assert w.begruendung == "Mac Studio und MacBook schlafen; der Auftrag kann erst laufen, wenn einer von ihnen wach ist."


def test_s53_schlafender_rechner_ist_kein_ausfall(welt):
    """Auch mit einem offenen Auftrag auf ihm löst ein schlafender Rechner weder "Umverteilen bei Ausfall" noch Engpass aus;
    eine Kopie auf ihm ist kein Doppel (sonst wiche womöglich die nutzbare auf dem wachen Rechner)."""
    from leitstelle.kern.lage import beurteilen
    from leitstelle.kern.regeln.bausteine import BAUSTEINE, Kontext
    from leitstelle.kern.werte import Lage
    v = welt.verbund
    a = welt.auftrag("rufzeichen", F.STIMME, laufzeit_s=60)
    welt.laufen(6)
    assert v.auftraege[a.kennung].zustand == Z.LAEUFT and v.auftraege[a.kennung].knoten == "mac-128"
    _einschlafen(v, "mac-128")
    assert BAUSTEINE["knoten_ausgefallen"].funktion(Kontext(verbund=v, messwerk=Messwerk(), instanz="")) == []
    assert beurteilen(v)[0] == Lage.RUHIG
    lade(welt, "glm@128")
    lade(welt, "glm@32")
    assert BAUSTEINE["modell_doppelt_geladen"].funktion(Kontext(verbund=v, messwerk=Messwerk(), instanz="")) == []
    v.knoten["mac-128"].schlaeft_seit_s = None                        # derselbe Fall ohne Schlaf: Ausfall
    assert len(BAUSTEINE["knoten_ausgefallen"].funktion(Kontext(verbund=v, messwerk=Messwerk(), instanz=""))) == 1
    assert len(BAUSTEINE["modell_doppelt_geladen"].funktion(Kontext(verbund=v, messwerk=Messwerk(), instanz=""))) == 1
    assert beurteilen(v)[0] == Lage.ENGPASS
