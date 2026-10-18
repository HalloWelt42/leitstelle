"""Jeder Zweig jeder Vorlage: Umleiten, Leerlauf räumen, Vorwärmen, Kette, Extern, Umverteilen,
Verlagern, Doppel, Hintergrund bei Lage. Szenarien S07, S09 bis S27 aus docs/SZENARIEN.md."""

import pytest

from leitstelle.kern.regeln import VORLAGEN, Kante, Knoten, Regelgraph, pruefen
from leitstelle.kern.werte import Auftragszustand as Z, Automatik, Dienstzustand, Faehigkeit as F, Massnahmenart as A, Massnahmenzustand as MZ, Modellzustand, Zone

from conftest import abschluesse, ausgefuehrt, entlade, gesperrt, lade, welt_mit


# ── Umleiten ─────────────────────────────────────────────────────────────

def test_s07_umleiten_mit_dienststart(welt):
    """Der Fall aus dem Entwurf: Bildauftrag wartet am Mac Studio, MacBook hat Platz, Dienst dort ist aus."""
    welt.auftrag("zusage", F.TEXT, laufzeit_s=60)
    k = welt.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    welt.laufen_bis_fertig(200)
    v = welt.verbund
    a = v.auftraege[k.kennung]
    assert a.zustand == Z.FERTIG and a.knoten == "mac-32" and a.umgeleitet == 1
    assert welt.wartezeit(k.kennung) < 25, "deutlich schneller als auf das Textmodell zu warten"
    m = ausgefuehrt(welt, A.UMLEITEN)
    assert len(m) == 1 and m[0].gewinn_s >= 2 * m[0].aufwand_s
    assert "Umgeleitet nach MacBook" in m[0].grund
    assert v.dienste["laeufer-32"].zustand == Dienstzustand.BEREIT
    assert "laeufer-32" in welt.messwerk.startzeiten and "glm-4.6v@mac-32" in welt.messwerk.ladezeiten
    assert any(art == "auftrag.laeuft" and app == "kiste" for _, app, art, _ in welt.signale)


def test_s09_umleiten_kein_platz_anderswo():
    w = welt_mit()
    w.verbund.knoten["mac-32"].budget_fest_gb = 4.0
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    w.laufen(60)
    assert not ausgefuehrt(w, A.UMLEITEN)
    assert "weiter warten" in abschluesse(w, "umleiten")
    assert w.verbund.auftraege[k.kennung].zustand == Z.WARTET_SPEICHER


def test_s10_umleiten_zone_nicht_erlaubt():
    w = welt_mit()
    w.verbund.knoten["mac-32"].zone = Zone.FERN      # Kiste darf nur Heimnetz
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    w.laufen(60)
    assert not ausgefuehrt(w, A.UMLEITEN)
    assert "weiter warten" in abschluesse(w, "umleiten")


def test_s11_umleiten_dienst_nicht_installiert():
    w = welt_mit()
    w.verbund.dienste["laeufer-32"].installiert = False
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    w.laufen(60)
    assert not ausgefuehrt(w, A.UMLEITEN)
    assert "weiter warten" in abschluesse(w, "umleiten")


def test_s12_umleiten_gewinn_zu_klein():
    """Laden auf dem MacBook ist gemessen langsam (60 s), das Textmodell wird bald frei: warten lohnt mehr.
    Danach räumt die Leerlauf-Regel nach der Bedarfsfrist den Platz am Mac Studio."""
    w = welt_mit()
    w.messwerk.merke_laufzeit("zusage", "text", 12.0)
    w.messwerk.merke_ladezeit("glm-4.6v", "mac-32", 60.0)
    w.auftrag("zusage", F.TEXT, laufzeit_s=12)
    w.laufen(6)
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    w.laufen(30)
    assert not ausgefuehrt(w, A.UMLEITEN)
    assert "warten lohnt mehr" in abschluesse(w, "umleiten")
    w.laufen_bis_fertig(300)
    assert ausgefuehrt(w, A.LEERLAUF_RAEUMEN), "nach der Bedarfsfrist weicht das ungenutzte Textmodell"
    assert w.verbund.auftraege[k.kennung].zustand == Z.FERTIG and w.verbund.auftraege[k.kennung].knoten == "mac-128"


def test_s12b_umleiten_dienst_laeuft_schon():
    w = welt_mit()
    w.verbund.dienste["laeufer-32"].zustand = Dienstzustand.BEREIT
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    w.laufen(40)
    # Läuft der Dienst schon, nimmt bereits der Zuteiler das MacBook (Laden ohne Entladen); kein Dienststart nötig
    assert w.verbund.auftraege[k.kennung].knoten == "mac-32"
    assert not w.startvorgaenge and w.verbund.dienste["laeufer-32"].zustand == Dienstzustand.BEREIT
    assert all("dienst_starten" not in " ".join(m.schritte) for m in ausgefuehrt(w))


# ── Leerlauf räumen ──────────────────────────────────────────────────────

def test_s16_leerlauf_raeumen_bei_bedarf():
    w = welt_mit()
    w.verbund.knoten["mac-32"].budget_fest_gb = 4.0           # kein Ausweichen
    w.verbund.modelle["qwen80@128"].letzte_nutzung_s = -10000  # lange ungenutzt
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5)
    w.laufen_bis_fertig(120)
    m = ausgefuehrt(w, A.LEERLAUF_RAEUMEN)
    assert len(m) == 1 and m[0].richtung == "entladen" and "Leerlauf geräumt" in m[0].grund
    v = w.verbund
    assert v.modelle["qwen80@128"].zustand == Modellzustand.FREI
    assert v.auftraege[k.kennung].zustand == Z.FERTIG and v.auftraege[k.kennung].knoten == "mac-128"


def test_s16b_leerlauf_raeumen_lohnt_nicht_wenn_platz_gleich_frei_wird():
    """Das rechnende Textmodell ist in wenigen Sekunden fertig; Räumen (Entladen und Laden) dauert länger:
    warten lohnt mehr. Sobald es fertig ist, räumt die Regel die ungenutzte Gemma-Kopie und der Auftrag läuft."""
    w = welt_mit()
    v = w.verbund
    v.knoten["mac-32"].budget_fest_gb = 4.0            # kein Ausweichen
    v.knoten["mac-128"].speicher_gb = 150.0            # Budget 118, 11 GB frei: GLM (11,8) passt erst, wenn Gemma (16,2) weicht
    lade(w, "gemma@128")
    w.messwerk.merke_laufzeit("zusage", "text", 20.0)
    w.auftrag("zusage", F.TEXT, laufzeit_s=20)
    w.laufen(1)
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5, festes_modell="glm-4.6v")
    w.laufen(14)
    assert "warten lohnt mehr" in abschluesse(w, "leerlauf_raeumen")
    assert not ausgefuehrt(w, A.LEERLAUF_RAEUMEN)
    w.laufen_bis_fertig(200)
    assert ausgefuehrt(w, A.LEERLAUF_RAEUMEN) and v.modelle["gemma@128"].zustand == Modellzustand.FREI
    assert v.modelle["qwen80@128"].zustand == Modellzustand.GELADEN, "das eben genutzte Textmodell bleibt (Bedarfsfrist)"
    assert v.auftraege[k.kennung].zustand == Z.FERTIG and v.auftraege[k.kennung].knoten == "mac-128"


def test_s17_leerlauf_nicht_bei_geschuetztem():
    w = welt_mit()
    w.verbund.knoten["mac-32"].budget_fest_gb = 4.0
    w.verbund.modelle["qwen80@128"].letzte_nutzung_s = -10000
    w.verbund.modelle["qwen80@128"].parameter_mrd = 8          # unter der Schutzgrenze
    w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5)
    w.laufen(60)
    assert not ausgefuehrt(w, A.LEERLAUF_RAEUMEN)
    assert "kein Leerlauf, der weichen darf" in abschluesse(w, "leerlauf_raeumen")
    assert w.verbund.modelle["qwen80@128"].zustand != Modellzustand.FREI


def test_s18_leerlauf_nicht_innerhalb_verweildauer():
    w = welt_mit()
    w.verbund.knoten["mac-32"].budget_fest_gb = 4.0
    w.verbund.modelle["qwen80@128"].letzte_nutzung_s = -10000
    w.verbund.modelle["qwen80@128"].geladen_seit_s = -30       # frisch geladen
    w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5)
    w.laufen(60)
    assert not ausgefuehrt(w, A.LEERLAUF_RAEUMEN)


def test_s19_leerlauf_nicht_bei_kuerzlicher_nutzung():
    w = welt_mit()
    w.verbund.knoten["mac-32"].budget_fest_gb = 4.0
    w.verbund.modelle["qwen80@128"].letzte_nutzung_s = -10     # gerade benutzt
    w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5)
    w.laufen(30)
    assert not ausgefuehrt(w, A.LEERLAUF_RAEUMEN)
    assert w.verbund.modelle["qwen80@128"].zustand == Modellzustand.GELADEN, "innerhalb der Bedarfsfrist wird nichts entladen"


# ── Vorwärmen ────────────────────────────────────────────────────────────

def test_s20_vorwaermen_bei_angehaltenem_hintergrund():
    w = welt_mit()
    entlade(w, "qwen80@128")
    w.verbund.hintergrund_an = False
    # Hintergrund-Lage-Regel würde den Hintergrund bei ruhiger Lage wieder einschalten: abschalten
    w.verbund.regelwerk.szenarien_an[A.HINTERGRUND_LAGE] = False
    t = w.auftrag("tubevault", F.TEXT, laufzeit_s=5)
    w.laufen(10)
    v = w.verbund
    assert v.auftraege[t.kennung].zustand == Z.EINGEREIHT
    assert ausgefuehrt(w, A.VORWAERMEN), "Modell wird geladen, obwohl der Auftrag noch wartet"
    w.laufen(40)
    assert v.modelle["qwen80@128"].zustand == Modellzustand.GELADEN
    w.verbund.hintergrund_an = True
    w.laufen(6)
    assert v.auftraege[t.kennung].zustand == Z.LAEUFT, "startet sofort, nichts mehr zu laden"


def test_s21_vorwaermen_ohne_platz():
    w = welt_mit()
    w.verbund.hintergrund_an = False
    w.verbund.regelwerk.szenarien_an[A.HINTERGRUND_LAGE] = False
    w.verbund.knoten["mac-32"].budget_fest_gb = 4.0
    w.auftrag("bildschmiede", F.BILD_BESCHREIBEN, laufzeit_s=5)   # Gemma, nirgends geladen, Mac Studio voll
    w.laufen(20)
    assert not ausgefuehrt(w, A.VORWAERMEN)
    assert "kein Platz ohne Entladen" in abschluesse(w, "vorwaermen")


# ── Kette ausweichen ─────────────────────────────────────────────────────

def test_s22_kette_ausweichen_auf_geladene_alternative():
    w = welt_mit()
    lade(w, "klein@128")
    w.auftrag("zusage", F.TEXT, laufzeit_s=90)
    w.laufen(6)
    z = w.auftrag("zusage", F.TEXT, laufzeit_s=5)
    w.laufen(20)
    v = w.verbund
    # "Geladene zuerst" gilt schon im Zuteiler: der zweite Auftrag nimmt das kleine Modell sofort
    assert v.auftraege[z.kennung].modell == "klein@128"
    # Mit ausgeschalteter Vorliebe für Geladenes greift die Regel Kette ausweichen
    w2 = welt_mit(geladene_zuerst=False)
    lade(w2, "klein@128")
    w2.auftrag("zusage", F.TEXT, laufzeit_s=90)
    w2.laufen(6)
    z2 = w2.auftrag("zusage", F.TEXT, laufzeit_s=5)
    w2.laufen(20)
    assert ausgefuehrt(w2, A.KETTE_AUSWEICHEN)
    assert w2.verbund.auftraege[z2.kennung].modell == "klein@128"


def test_s23_kette_nicht_bei_festem_modell():
    w = welt_mit()
    lade(w, "klein@128")
    w.auftrag("zusage", F.TEXT, laufzeit_s=90)
    w.laufen(6)
    z = w.auftrag("zusage", F.TEXT, laufzeit_s=5, festes_modell="qwen-next-80b")
    w.laufen(20)
    assert not ausgefuehrt(w, A.KETTE_AUSWEICHEN)
    assert w.verbund.auftraege[z.kennung].zustand == Z.EINGEREIHT


# ── Extern ausweichen ────────────────────────────────────────────────────

def test_s24_extern_ausweichen_ueber_schwelle():
    w = welt_mit(extern_schwelle_s=30)
    w.messwerk.merke_laufzeit("zusage", "text", 300.0)
    w.auftrag("zusage", F.TEXT, laufzeit_s=300)
    w.laufen(6)
    ohne = w.auftrag("fundus", F.TEXT, laufzeit_s=5)                       # ohne Erlaubnisliste der App: nie extern
    f = w.auftrag("fundus", F.TEXT, laufzeit_s=5, extern=["qwen-35b-extern"])
    w.laufen(20)
    v = w.verbund
    assert not v.auftraege[ohne.kennung].extern
    assert ausgefuehrt(w, A.EXTERN_AUSWEICHEN)
    assert v.auftraege[f.kennung].extern and v.auftraege[f.kennung].dienst == "extern-anbieter"
    w.laufen_bis_fertig(60)
    assert v.auftraege[f.kennung].zustand == Z.FERTIG


def test_s25_extern_nicht_erlaubt_und_unter_schwelle():
    w = welt_mit(extern_schwelle_s=30)
    w.messwerk.merke_laufzeit("zusage", "text", 300.0)
    w.auftrag("zusage", F.TEXT, laufzeit_s=300)
    w.laufen(6)
    k = w.auftrag("kiste", F.TEXT, laufzeit_s=5)          # darf nicht extern
    w.laufen(20)
    assert "Anwendung darf nicht extern" in abschluesse(w, "extern_ausweichen")
    assert not w.verbund.auftraege[k.kennung].extern
    # unter der Schwelle: Fundus wartet nur kurz
    w2 = welt_mit(extern_schwelle_s=120)
    w2.messwerk.merke_laufzeit("zusage", "text", 20.0)
    w2.auftrag("zusage", F.TEXT, laufzeit_s=20)
    w2.laufen(6)
    w2.auftrag("fundus", F.TEXT, laufzeit_s=5, extern=["qwen-35b-extern"])
    w2.laufen(10)
    assert "Wartezeit unter der Schwelle" in abschluesse(w2, "extern_ausweichen")
    assert not ausgefuehrt(w2, A.EXTERN_AUSWEICHEN)


def test_s25b_extern_kein_dienst():
    """Fundus darf extern und wartet lange, aber der externe Anbieter ist nicht erreichbar: der Zweig endet ohne Maßnahme."""
    w = welt_mit(extern_schwelle_s=30)
    w.verbund.dienste["extern-anbieter"].zustand = Dienstzustand.NICHT_ERREICHBAR
    w.messwerk.merke_laufzeit("zusage", "text", 300.0)
    w.auftrag("zusage", F.TEXT, laufzeit_s=300)
    w.laufen(6)
    f = w.auftrag("fundus", F.TEXT, laufzeit_s=5, extern=["qwen-35b-extern"])
    w.laufen(20)
    assert "kein externer Dienst" in abschluesse(w, "extern_ausweichen")
    assert not ausgefuehrt(w, A.EXTERN_AUSWEICHEN)
    assert w.verbund.auftraege[f.kennung].zustand == Z.EINGEREIHT and not w.verbund.auftraege[f.kennung].extern


# ── Umverteilen bei Ausfall ──────────────────────────────────────────────

def test_s26_umverteilen_bei_knotenausfall():
    w = welt_mit()
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=60)   # wird auf das MacBook umgeleitet
    w.laufen(30)
    v = w.verbund
    assert v.auftraege[k.kennung].zustand == Z.LAEUFT and v.auftraege[k.kennung].knoten == "mac-32"
    v.knoten["mac-32"].erreichbar = False
    w.laufen(10)
    assert ausgefuehrt(w, A.UMVERTEILEN)
    a = v.auftraege[k.kennung]
    assert a.zustand == Z.ABGEBROCHEN and a.teilergebnis
    assert any(art == "auftrag.abgebrochen" and n.get("teilergebnis") for _, _, art, n in w.signale)


# ── Verlagern im Zeitfenster ─────────────────────────────────────────────

def test_s27_verlagern_zeitfenster():
    w = welt_mit()
    w.verbund.stunde = 23
    w.laufen(6)
    assert w.verbund.hintergrund_knoten_bevorzugt == "mac-32"
    assert ausgefuehrt(w, A.VERLAGERN)
    w.verbund.stunde = 9
    w.laufen(6)
    assert w.verbund.hintergrund_knoten_bevorzugt is None



def test_s27b_ueberschneidende_fenster_zweier_rechner():
    """Zwei Rechner mit überschneidenden Fenstern: der Vorzug bleibt beim ersten, solange dessen Fenster gilt, statt im
    Takt hin und her zu springen (Prüfung auf einen zweiten Mac, 18.10.2026)."""
    w = welt_mit()
    w.verbund.knoten["mac-128"].hintergrund_fenster = (22, 6)
    w.verbund.stunde = 23
    w.laufen(60)
    assert len(ausgefuehrt(w, A.VERLAGERN)) == 1
    assert not gesperrt(w), "kein Flattern, das den Schleifenschutz auslöst"


# ── Doppel auflösen ──────────────────────────────────────────────────────

def test_s29_doppel_aufloesen_bei_bedarf():
    """Gemma liegt auf beiden Macs; auf dem MacBook wartet GLM auf Platz, Gemma dort ist ungenutzt: die Kopie weicht."""
    w = welt_mit()
    v = w.verbund
    v.dienste["laeufer-32"].zustand = Dienstzustand.BEREIT
    lade(w, "gemma@128")
    lade(w, "gemma@32")                               # MacBook: 16,2 + 1,5 belegt, Budget 24, frei 6,3
    v.knoten["mac-128"].budget_fest_gb = 4.0           # Mac Studio kann GLM nicht aufnehmen
    v.regelwerk.szenarien_an[A.LEERLAUF_RAEUMEN] = False   # sonst räumt die Leerlauf-Regel zuerst
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5, festes_modell="glm-4.6v")
    w.laufen(20)
    m = ausgefuehrt(w, A.DOPPEL_AUFLOESEN)
    assert m and m[0].richtung == "entladen"
    assert v.modelle["gemma@32"].zustand == Modellzustand.FREI
    assert v.modelle["gemma@128"].zustand == Modellzustand.GELADEN, "die andere Kopie bleibt"
    w.laufen_bis_fertig(120)
    assert v.auftraege[k.kennung].zustand == Z.FERTIG and v.auftraege[k.kennung].knoten == "mac-32"


def test_s30_doppel_ohne_bedarf_bleibt():
    w = welt_mit()
    w.verbund.dienste["laeufer-32"].zustand = Dienstzustand.BEREIT
    lade(w, "gemma@128")
    lade(w, "gemma@32")
    w.laufen(20)
    assert not ausgefuehrt(w, A.DOPPEL_AUFLOESEN)
    assert "kein Bedarf, Kopie bleibt" in abschluesse(w, "doppel_aufloesen")
    # GLM ist unter 10 Milliarden und damit geschützt: wird nie als Doppel aufgelöst
    lade(w, "glm@128")
    lade(w, "glm@32")
    w.laufen(10)
    assert "beide Kopien in Gebrauch oder geschützt" in abschluesse(w, "doppel_aufloesen")


# ── Hintergrund bei Lage ─────────────────────────────────────────────────

def test_s31_hintergrund_bei_angespannter_lage_angehalten_und_fortgesetzt():
    w = welt_mit()
    w.verbund.knoten["mac-32"].budget_fest_gb = 4.0
    w.verbund.regelwerk.szenarien_an[A.LEERLAUF_RAEUMEN] = False
    t = w.auftrag("tubevault", F.HOEREN, laufzeit_s=100)      # läuft auf txt2voice
    w.laufen(6)
    assert w.verbund.auftraege[t.kennung].zustand == Z.LAEUFT
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5)   # wartet auf Speicher -> Lage angespannt
    w.laufen(6)
    assert not w.verbund.hintergrund_an
    assert w.verbund.auftraege[t.kennung].zustand == Z.PAUSIERT
    w.verbund.auftraege[k.kennung].zustand = Z.ABGEBROCHEN    # Lage wieder ruhig
    w.laufen(10)
    assert w.verbund.hintergrund_an
    assert w.verbund.auftraege[t.kennung].zustand in (Z.ZUGETEILT, Z.LAEUFT)


# ── Automatik, Graphprüfung ──────────────────────────────────────────────

def test_s32_automatik_vorschlagen_plant_nur():
    w = welt_mit(automatik=Automatik.VORSCHLAGEN)
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    w.laufen(30)
    geplant = [m for m in w.verbund.massnahmen if m.zustand == MZ.GEPLANT and m.art == A.UMLEITEN]
    assert geplant and not ausgefuehrt(w)
    assert w.verbund.auftraege[k.kennung].zustand == Z.WARTET_SPEICHER


def test_s33_automatik_aus_wertet_nicht_aus():
    w = welt_mit(automatik=Automatik.AUS)
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    w.laufen(30)
    assert not w.verbund.massnahmen


def test_s41_graphpruefung_findet_fehler():
    for g in VORLAGEN:
        assert pruefen(g) == []
    g = Regelgraph(kennung="x", name="x", art=A.UMLEITEN, knoten=[
        Knoten(id="a", art="ausloeser", baustein="auftrag_wartet"),
        Knoten(id="p", art="pruefung", baustein="immer"),
        Knoten(id="k", art="aktion", baustein="melden"),
    ], kanten=[Kante(von="a", nach="p"), Kante(von="p", nach="k", port="ja"), Kante(von="k", nach="p")])
    fehler = pruefen(g)
    assert any("Zyklus" in f for f in fehler)
    assert any("ja und nein" in f for f in fehler)
    g2 = Regelgraph(kennung="y", name="y", art=A.UMLEITEN, knoten=[Knoten(id="a", art="ausloeser", baustein="gibt_es_nicht"), Knoten(id="e", art="ende")],
                    kanten=[Kante(von="a", nach="e")])
    assert any("unbekannter Baustein" in f for f in pruefen(g2))
    with pytest.raises(ValueError):
        from leitstelle.kern.regeln import auswerten
        from leitstelle.kern.messungen import Messwerk
        auswerten(g, welt_mit().verbund, Messwerk())



# ── Weitere Instanz (ZUSAMMENSPIEL Z3) ───────────────────────────────────

def test_weitere_instanz_bei_andrang():
    """Ein kleiner Dienst erlaubt zwei Instanzen und ist belegt; ein zweiter Auftrag wartet länger als die Schwelle:
    die Leitstelle startet die zweite Instanz, der Auftrag läuft dort. Mehr als die Höchstzahl gibt es nie."""
    w = welt_mit()
    v = w.verbund
    grund = v.modelle["whisperm@32"]
    grund.instanzen_hoechstens, grund.geschuetzt_fest, grund.plaetze = 2, False, 1
    v.dienste["hoerer-32"].plaetze = 1
    w.messwerk.merke_laufzeit("rufzeichen", "hoeren", 300.0)
    erster = w.auftrag("rufzeichen", F.HOEREN, laufzeit_s=300, festes_modell="whisper-mittel")
    w.laufen(3)
    zweiter = w.auftrag("rufzeichen", F.HOEREN, laufzeit_s=10, festes_modell="whisper-mittel")
    dritter = w.auftrag("rufzeichen", F.HOEREN, laufzeit_s=10, festes_modell="whisper-mittel")
    w.laufen(60)
    assert ausgefuehrt(w, A.WEITERE_INSTANZ), abschluesse(w, "weitere_instanz")
    instanzen = v.instanzen("whisper-mittel", "mac-32")
    assert len(instanzen) == 2 and sum(m.zusatz for m in instanzen) == 1
    zusatz = next(m for m in instanzen if m.zusatz)
    w.laufen_bis_fertig(900)
    assert v.auftraege[zweiter.kennung].modell == zusatz.kennung or v.auftraege[dritter.kennung].modell == zusatz.kennung
    assert "alle 2 Instanzen laufen" in abschluesse(w, "weitere_instanz") or len(ausgefuehrt(w, A.WEITERE_INSTANZ)) == 1
    assert v.auftraege[erster.kennung].zustand == Z.FERTIG


def test_weitere_instanz_weicht_zuerst():
    """Bei Speichermangel weicht eine weitere Instanz vor allen anderen Modellen, auch vor größeren."""
    from leitstelle.kern.messungen import Messwerk
    from leitstelle.kern.speicherplaner import planen
    w = welt_mit()
    v = w.verbund
    grund = v.modelle["qwen80@128"]
    zusatz = grund.model_copy(update={"kennung": "kleiner.2@laeufer-128", "familie": "klein", "gb": 2.0, "zusatz": True,
                                      "geschuetzt_fest": False, "parameter_mrd": 20})
    v.modelle[zusatz.kennung] = zusatz
    plan = planen(v, "mac-128", 11.8, Messwerk(), familie="glm-4.6v")
    assert plan.entladen[0] == zusatz.kennung
