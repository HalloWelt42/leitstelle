"""Last des Modell-Läufers und des Rechners (ZUSAMMENSPIEL Z6) in der Schein-Welt: Regel "Läufer arbeitet ohne Auftrag"
(Vorgabe aus) und Regel "Hintergrund bei Rechnerlast" (Vorgabe an). Szenarien L01 bis L14 aus docs/SZENARIEN.md.

Die Meldungen `knoten.last` des Maschinenraums kommen hier im Takt der Beobachtung (15 s) über denselben Weg in den
Verbund wie im Betrieb (`last_uebernehmen`)."""

from __future__ import annotations

from leitstelle.kern.modelle import Prozesslast
from leitstelle.kern.rechnerlast import last_uebernehmen, ohne_auftrag
from leitstelle.kern.werte import Auftragszustand as Z, Faehigkeit as F, Hintergrundstufe as S, Laeuferrolle as R, Massnahmenart as A
from leitstelle.kern.werte import Modellzustand, Prioritaet as P
from leitstelle.simulation import Welt

from conftest import abschluesse, ausgefuehrt, gesperrt, welt_mit

TAKT_S = 15
BGE = "~/.lmstudio/models/lmstudio-community/bge-m3-GGUF/bge-m3-Q8_0.gguf"
HAUPT = (807, R.HAUPT, 100.0, "")
SONSTIG = (810, R.SONSTIG, 90.0, "")


def melden(w: Welt, prozesse: list[tuple[int, R, float | None, str]], fremd: float | None = 10.0, knoten: str = "mac-128") -> None:
    """Eine Meldung knoten.last des Maschinenraums: (pid, Rolle, Prozent eines Kerns, Modelldatei) je Prozess."""
    liste = [Prozesslast(pid=pid, name="node (Läufer)" if rolle == R.ARBEITER else "Läufer", rolle=rolle, modelldatei=datei, gb=1.2,
                         cpu_prozent=cpu) for pid, rolle, cpu, datei in prozesse]
    last_uebernehmen(w.verbund, knoten, True, 10, liste, fremd)


def laufen(w: Welt, sekunden: float, prozesse, fremd: float | None = 10.0) -> None:
    """Die Welt laufen lassen; alle 15 s meldet der Maschinenraum dieselbe Last."""
    for _ in range(int(sekunden // TAKT_S)):
        melden(w, prozesse(w) if callable(prozesse) else prozesse, fremd)
        w.laufen(TAKT_S)


def regel_an(w: Welt) -> Welt:
    w.verbund.regelwerk.szenarien_an[A.LAEUFER_OHNE_AUFTRAG] = True
    return w


HAENGT = [HAUPT, (808, R.ARBEITER, 100.0, BGE), (809, R.ARBEITER, 2.0, BGE), SONSTIG]


# ── Läufer arbeitet ohne Auftrag ─────────────────────────────────────────

def test_l01_beendet_erst_nach_voller_frist_und_nur_einmal():
    w = regel_an(welt_mit())
    laufen(w, 285, HAENGT)
    assert w.beendet == [] and not ausgefuehrt(w, A.LAEUFER_OHNE_AUFTRAG)
    assert not ohne_auftrag(w.verbund, w.verbund.knoten["mac-128"])        # 285 s: noch keine volle Frist
    laufen(w, 60, HAENGT)
    assert [(k, pid) for _, k, pid in w.beendet] == [("mac-128", 808)]       # nur der Arbeiter über der Schwelle
    m = ausgefuehrt(w, A.LAEUFER_OHNE_AUFTRAG)
    assert len(m) == 1 and m[0].richtung == "beenden"
    assert m[0].grund == "Läufer auf Mac Studio: node (Läufer) mit bge-m3-Q8_0.gguf rechnete 5 min ohne Auftrag mit 1,0 Kernen; wird beendet"
    laufen(w, 120, HAENGT)                                                   # der Maschinenraum meldet ihn noch: kein zweites Mal
    assert len(w.beendet) == 1


def test_l02_nicht_bei_einer_umgehung_am_laeufer():
    """Spricht ein Programm den Läufer am Leitstand vorbei an, rechnet der Arbeiter vermutlich für diesen Kunden."""
    w = regel_an(welt_mit())
    w.verbund.knoten["mac-128"].laeufer_umgehungen = ["skript.py (Prozess 980)"]
    laufen(w, 360, HAENGT)
    assert w.beendet == [] and not ausgefuehrt(w, A.LAEUFER_OHNE_AUFTRAG)
    assert "rechnet für ein Programm am Leitstand vorbei, nicht beendet" in abschluesse(w, "laeufer_ohne_auftrag")
    assert [p.pid for p in ohne_auftrag(w.verbund, w.verbund.knoten["mac-128"])] == [808]   # der Befund bleibt sichtbar


def test_l03_nicht_solange_ein_auftrag_lief_frist_ab_seinem_ende():
    """Ein Auftrag der Leitstelle auf dem Läufer (hier eine Einbettung von 100 s) hält die Regel an; die Frist zählt ab
    seinem Ende."""
    w = regel_an(welt_mit())
    laufen(w, 90, HAENGT)
    w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=100)
    laufen(w, 240, HAENGT)                                                   # 330 s: über der Schwelle seit 330 s, Auftrag bis etwa 195 s
    assert w.beendet == []
    ende = w.verbund.modelle["bge@128"].letzte_nutzung_s
    laufen(w, ende + 300 - w.verbund.zeit_s - TAKT_S, HAENGT)
    assert w.beendet == []
    laufen(w, 45, HAENGT)
    assert len(w.beendet) == 1


def test_l04_vorgabe_aus_nur_befund():
    w = welt_mit()
    laufen(w, 360, HAENGT)
    assert w.beendet == [] and not ausgefuehrt(w, A.LAEUFER_OHNE_AUFTRAG)
    assert [p.pid for p in ohne_auftrag(w.verbund, w.verbund.knoten["mac-128"])] == [808]


def test_l05_hauptprozess_und_sonstiges_nie():
    w = regel_an(welt_mit())
    laufen(w, 360, [HAUPT, SONSTIG])
    assert w.beendet == [] and not ohne_auftrag(w.verbund, w.verbund.knoten["mac-128"])


def test_l06_einmal_unter_der_schwelle_beginnt_die_frist_neu():
    w = regel_an(welt_mit())
    laufen(w, 240, HAENGT)
    laufen(w, 15, [HAUPT, (808, R.ARBEITER, 30.0, BGE)])
    laufen(w, 240, HAENGT)
    assert w.beendet == []


def test_l07_derselbe_haenger_kurz_danach_ist_flattern():
    """Der Läufer lädt das Modell neu, und der neue Arbeiter hängt wieder: das zweite Beenden innerhalb des Fensters sperrt
    die Regel für dieses Modell auf dem Rechner (Schleifenschutz wie bei allen Regeln)."""
    w = regel_an(welt_mit())
    laufen(w, 345, HAENGT)
    assert len(w.beendet) == 1
    laufen(w, 330, [HAUPT, (812, R.ARBEITER, 100.0, BGE)])
    assert len(w.beendet) == 1
    assert any(f"Flattern erkannt: {BGE}@mac-128" in m.grund and "beendet" in m.grund for m in gesperrt(w))


# ── Hintergrund bei Rechnerlast ──────────────────────────────────────────

def _stufen(w: Welt, folge: list[float]) -> list[S]:
    """Je Fremdlast 75 s lang melden (das Mittel über 60 s ist dann diese Last); die Stufe danach."""
    aus = []
    for fremd in folge:
        laufen(w, 75, [HAUPT], fremd)
        aus.append(w.verbund.knoten["mac-128"].hintergrund_stufe)
    return aus


def test_l10_drosseln_anhalten_und_zurueck_erst_mit_abstand():
    w = welt_mit()
    assert _stufen(w, [30, 55, 80, 70, 60, 45, 35]) == [S.FREI, S.GEDROSSELT, S.ANGEHALTEN, S.ANGEHALTEN, S.GEDROSSELT, S.GEDROSSELT, S.FREI]
    gruende = [m.grund for m in ausgefuehrt(w, A.HINTERGRUND_RECHNERLAST)]
    assert gruende == ["Hintergrund auf Mac Studio gedrosselt (vorher frei): Fremdlast im Mittel 55 %, drosseln ab 50 %",
                       "Hintergrund auf Mac Studio angehalten (vorher gedrosselt): Fremdlast im Mittel 80 %, anhalten ab 75 %",
                       "Hintergrund auf Mac Studio gedrosselt (vorher angehalten): Fremdlast im Mittel 62 %, drosseln ab 40 %",
                       "Hintergrund auf Mac Studio freigegeben (vorher gedrosselt): Fremdlast im Mittel 38 %, frei unter 40 %"]
    assert w.verbund.knoten["mac-32"].hintergrund_stufe == S.FREI          # andere Rechner unberührt


def test_l11_angehalten_teilt_hintergrund_nicht_zu_auch_nicht_nach_der_fairness():
    w = welt_mit()
    _stufen(w, [90])
    hinten = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=10, prioritaet=P.HINTERGRUND)
    vorn = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=10)
    laufen(w, w.verbund.regelwerk.hintergrund_spaetestens_s + 60, [HAUPT], 90)
    v = w.verbund
    assert v.auftraege[vorn.kennung].zustand == Z.FERTIG                     # Normales unberührt
    assert v.auftraege[hinten.kennung].zustand == Z.EINGEREIHT
    assert v.auftraege[hinten.kennung].begruendung.startswith("Hintergrund auf Mac Studio angehalten: Fremdlast 90 %")
    laufen(w, 75, [HAUPT], 20)
    w.laufen_bis_fertig(120)
    assert v.auftraege[hinten.kennung].zustand == Z.FERTIG


def test_l12_laufender_hintergrund_rechnet_zu_ende():
    w = welt_mit()
    a = w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=200, prioritaet=P.HINTERGRUND)
    w.laufen(10)
    assert w.verbund.auftraege[a.kennung].zustand == Z.LAEUFT
    _stufen(w, [90])
    assert w.verbund.auftraege[a.kennung].zustand == Z.LAEUFT
    w.laufen_bis_fertig(300)
    assert w.verbund.auftraege[a.kennung].zustand == Z.FERTIG


def _einbettung(hoechstens: int = 4) -> Welt:
    w = welt_mit()
    v = w.verbund
    v.modelle["bge@128"].instanzen_hoechstens = hoechstens
    v.dienste["laeufer-128"].einbettung_spielraum_gb = 1.0
    v.anwendungen["fundus"].gleichzeitig = 8
    w.messwerk.merke_laufzeit("fundus", "einbettung", 30.0)
    return w


def test_l13_gedrosselt_keine_weitere_instanz_fuer_hintergrund_normales_wie_immer():
    w = _einbettung()
    _stufen(w, [60])
    for _ in range(4):
        w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=30, prioritaet=P.HINTERGRUND)
    laufen(w, 45, [HAUPT], 60)
    v = w.verbund
    assert not ausgefuehrt(w, A.EINBETTUNG_VERSTAERKEN)
    assert [m.kennung for m in v.instanzen("bge-m3", "mac-128")] == ["bge@128"]
    assert any(a.zustand == Z.LAEUFT for a in v.auftraege.values())         # die Grundinstanz arbeitet weiter
    for _ in range(3):
        w.auftrag("fundus", F.EINBETTUNG, laufzeit_s=30)
    laufen(w, 45, [HAUPT], 60)
    assert ausgefuehrt(w, A.EINBETTUNG_VERSTAERKEN), "Normales darf weitere Instanzen bekommen"


def test_l14_gedrosselt_weitere_instanzen_ohne_auftrag_sofort_entladen():
    w = _einbettung()
    v = w.verbund
    grund = v.modelle["bge@128"]
    zusatz = grund.model_copy(update={"kennung": "bge-m3.2@laeufer-128", "name": "bge-m3 (2)", "zusatz": True, "zustand": Modellzustand.GELADEN,
                                      "geladen_seit_s": 0.0, "letzte_nutzung_s": 0.0})
    v.modelle[zusatz.kennung] = zusatz
    w.laufen(30)
    assert zusatz.zustand == Modellzustand.GELADEN                           # frei: erst nach der Ruhezeit
    _stufen(w, [60])
    assert zusatz.zustand == Modellzustand.FREI
    m = ausgefuehrt(w, A.EINBETTUNG_ZURUECKBAUEN)
    assert len(m) == 1 and m[0].grund.endswith("Hintergrund gedrosselt, kein Auftrag")


def test_l15_ohne_messung_wird_freigegeben():
    w = welt_mit()
    _stufen(w, [90])
    w.verbund.knoten["mac-128"].last = None                                  # Maschinenraum getrennt
    w.laufen(10)
    k = w.verbund.knoten["mac-128"]
    assert k.hintergrund_stufe == S.FREI and k.hintergrund_grund == "Fremdlast nicht mehr gemessen"


def test_l16_regel_aus_laesst_die_stufe():
    w = welt_mit()
    w.verbund.regelwerk.szenarien_an[A.HINTERGRUND_RECHNERLAST] = False
    assert _stufen(w, [90]) == [S.FREI]


def test_l17_gespeichertes_regelwerk_ohne_die_neuen_szenarien():
    from leitstelle.kern.modelle import Regelwerk
    r = Regelwerk.model_validate({"szenarien_an": {"umleiten": False}})
    assert r.szenarien_an[A.LAEUFER_OHNE_AUFTRAG] is False and r.szenarien_an[A.HINTERGRUND_RECHNERLAST] is True
    assert r.szenarien_an[A.UMLEITEN] is False

