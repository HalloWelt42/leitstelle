"""Bausteine der Regelgraphen: Auslöser, Prüfungen, Aktionen.

Jeder Baustein ist eine kleine, typisierte Funktion über einem Kontext. Auslöser liefern
Instanzen (zum Beispiel je wartendem Auftrag einen Kontext), Prüfungen liefern ja oder nein
und schreiben Zwischenwerte in den Kontext, Aktionen beschreiben, was zu tun wäre. Nichts hier
verändert den Verbund; das tut der Vollzug im Umschichter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..messungen import Messwerk
from ..modelle import Auftrag, Modell, Verbund
from ..rechnerlast import STUFENRANG, datei, dauer, fremd_mittel, kerne, ohne_auftrag, ohne_auftrag_seit, prozent
from ..speicherplaner import planen
from ..werte import Auftragszustand, Dienstzustand, Faehigkeit, Hintergrundstufe, Lage, Modellzustand, Prioritaet, Zone
from ..zuteiler import hintergrund_gebremst, wirksame_prioritaet
from .. import lage as lagebeurteilung
from ..text import komma


@dataclass
class Kontext:
    """Was ein Regellauf gerade betrachtet; Prüfungen füllen Zielknoten, Modell und Zahlen."""

    verbund: Verbund
    messwerk: Messwerk
    instanz: str = ""
    auftrag: Auftrag | None = None
    knoten_quelle: str | None = None
    knoten_ziel: str | None = None
    dienst_ziel: str | None = None
    modell_ziel: str | None = None
    modelle_entladen: list[str] = field(default_factory=list)
    gewinn_s: float = 0.0
    aufwand_s: float = 0.0
    werte: dict[str, Any] = field(default_factory=dict)
    lage: Lage | None = None

    @property
    def r(self):
        return self.verbund.regelwerk


@dataclass(frozen=True)
class Baustein:
    name: str
    art: str                      # ausloeser, pruefung, aktion
    wort: str
    erklaerung: str
    funktion: Callable[..., Any]
    parameter: dict[str, Any] = field(default_factory=dict)


BAUSTEINE: dict[str, Baustein] = {}


def baustein(name: str, art: str, wort: str, erklaerung: str, **parameter: Any):
    def registrieren(f: Callable[..., Any]) -> Callable[..., Any]:
        BAUSTEINE[name] = Baustein(name=name, art=art, wort=wort, erklaerung=erklaerung, funktion=f, parameter=parameter)
        return f
    return registrieren


# ── Hilfen ───────────────────────────────────────────────────────────────

def erlaubte_zone(verbund: Verbund, auftrag: Auftrag, knoten: str) -> bool:
    k = verbund.knoten[knoten]
    return k.erreichbar and k.zone in verbund.anwendungen[auftrag.anwendung].zonen


def instanz_der_familie(verbund: Verbund, familie: str, faehigkeit, knoten: str) -> Modell | None:
    for m in verbund.modelle_auf(knoten):
        if m.familie == familie and faehigkeit in m.faehigkeiten:
            return m
    return None


def erwartete_wartezeit(k: Kontext, a: Auftrag) -> float:
    """Wie lange der Auftrag an seinem bisherigen Platz voraussichtlich noch wartet (aus Messungen und Regeln)."""
    if a.voraussichtlich_s is not None:
        return a.voraussichtlich_s
    v = k.verbund
    if a.wartet_auf_familie and a.wartet_auf_knoten:
        m = instanz_der_familie(v, a.wartet_auf_familie, a.faehigkeit, a.wartet_auf_knoten)
        if m and m.im_speicher:
            belegt = v.belegung(m.kennung)
            if belegt:
                return max(k.messwerk.rest_s(x.anwendung, x.faehigkeit.value, x.fortschritt_s) for x in belegt)
        if a.zustand == Auftragszustand.WARTET_SPEICHER:
            # Platz wird frei, wenn ein blockierendes Modell fertig rechnet oder seine Leerlauf-Frist abläuft
            fristen = []
            for b in v.modelle_auf(a.wartet_auf_knoten):
                if not b.im_speicher or b.geschuetzt(k.r.schutzgrenze_mrd):
                    continue
                belegt = v.belegung(b.kennung)
                if belegt:
                    fristen.append(max(k.messwerk.rest_s(x.anwendung, x.faehigkeit.value, x.fortschritt_s) for x in belegt) + k.messwerk.entladezeit_s)
                elif b.letzte_nutzung_s is not None:
                    fristen.append(max(0.0, k.r.bedarfsfrist_s - (v.zeit_s - b.letzte_nutzung_s)) + k.messwerk.entladezeit_s + k.messwerk.ladezeit_schaetzung(m.gb if m else 0.0))
            if fristen:
                return min(fristen)
            return 3600.0
    return k.messwerk.laufzeit(a.anwendung, a.faehigkeit.value).sekunden


# ── Auslöser ─────────────────────────────────────────────────────────────

@baustein("auftrag_wartet_speicher", "ausloeser", "Auftrag wartet auf Speicher", "Je Auftrag, der auf Speicher wartet, ein Lauf.", mindestens_s=0.0)
def auftrag_wartet_speicher(k: Kontext, mindestens_s: float = 0.0) -> list[Kontext]:
    aus = []
    for a in k.verbund.wartende_auftraege():
        if a.zustand == Auftragszustand.WARTET_SPEICHER and k.verbund.zeit_s - a.eingang_s >= mindestens_s:
            aus.append(Kontext(verbund=k.verbund, messwerk=k.messwerk, instanz=a.kennung, auftrag=a, knoten_quelle=a.wartet_auf_knoten))
    return aus


@baustein("auftrag_wartet_auf_platz", "ausloeser", "Auftrag wartet auf ein belegtes Modell", "Je Auftrag, dessen Modell geladen, aber belegt ist, ein Lauf.", mindestens_s=0.0)
def auftrag_wartet_auf_platz(k: Kontext, mindestens_s: float = 0.0) -> list[Kontext]:
    aus = []
    for a in k.verbund.wartende_auftraege():
        if a.zustand == Auftragszustand.EINGEREIHT and a.wartet_auf_familie and k.verbund.zeit_s - a.eingang_s >= mindestens_s:
            aus.append(Kontext(verbund=k.verbund, messwerk=k.messwerk, instanz=a.kennung, auftrag=a, knoten_quelle=a.wartet_auf_knoten))
    return aus


@baustein("auftrag_wartet", "ausloeser", "Auftrag wartet", "Je wartendem Auftrag (Speicher oder Platz) ein Lauf.", mindestens_s=0.0)
def auftrag_wartet(k: Kontext, mindestens_s: float = 0.0) -> list[Kontext]:
    return auftrag_wartet_speicher(k, mindestens_s) + auftrag_wartet_auf_platz(k, mindestens_s)


@baustein("auftrag_eingereiht_ohne_modell", "ausloeser", "Eingereihter Auftrag, Modell nirgends geladen", "Aufträge, die aus anderen Gründen warten (Kontingent, Hintergrund) und deren Modell nicht geladen ist.")
def auftrag_eingereiht_ohne_modell(k: Kontext) -> list[Kontext]:
    aus = []
    for a in k.verbund.wartende_auftraege():
        if a.zustand != Auftragszustand.EINGEREIHT or a.wartet_auf_familie:
            continue
        fam = k.verbund.erste_familie(a)
        if not fam:
            continue
        if any(m.familie == fam and m.im_speicher for m in k.verbund.modelle.values()):
            continue
        aus.append(Kontext(verbund=k.verbund, messwerk=k.messwerk, instanz=a.kennung, auftrag=a))
    return aus


@baustein("knoten_ausgefallen", "ausloeser", "Knoten fällt aus", "Je nicht erreichbarem Knoten mit offenen Aufträgen ein Lauf; ein schlafender Rechner ist kein Ausfall.")
def knoten_ausgefallen(k: Kontext) -> list[Kontext]:
    aus = []
    for kn in k.verbund.knoten.values():
        if not kn.erreichbar and not kn.schlaeft and any(a.knoten == kn.kennung and a.offen for a in k.verbund.auftraege.values()):
            aus.append(Kontext(verbund=k.verbund, messwerk=k.messwerk, instanz=kn.kennung, knoten_quelle=kn.kennung))
    return aus


def _im_fenster(kn, stunde: int) -> bool:
    if not kn.hintergrund_fenster or not kn.erreichbar:
        return False
    von, bis = kn.hintergrund_fenster
    return von <= stunde < bis if von < bis else (stunde >= von or stunde < bis)


@baustein("zeitfenster_beginnt", "ausloeser", "Zeitfenster beginnt", "Ein Knoten hat ein Zeitfenster für Hintergrundarbeit, das jetzt gilt.")
def zeitfenster_beginnt(k: Kontext) -> list[Kontext]:
    """Höchstens ein bevorzugter Knoten: solange sein Fenster gilt, bleibt er es, auch wenn sich das Fenster eines
    anderen überschneidet (sonst sprang der Vorzug mit zwei Rechnern in jedem Takt hin und her)."""
    aus = []
    bevorzugt = k.verbund.knoten.get(k.verbund.hintergrund_knoten_bevorzugt or "")
    vergeben = bevorzugt is not None and _im_fenster(bevorzugt, k.verbund.stunde)
    for kn in sorted(k.verbund.knoten.values(), key=lambda x: x.kennung):
        if not kn.hintergrund_fenster or not kn.erreichbar:
            continue
        drin = _im_fenster(kn, k.verbund.stunde)
        if drin and not vergeben:
            aus.append(Kontext(verbund=k.verbund, messwerk=k.messwerk, instanz=kn.kennung, knoten_ziel=kn.kennung))
            vergeben = True
        if not drin and k.verbund.hintergrund_knoten_bevorzugt == kn.kennung:
            aus.append(Kontext(verbund=k.verbund, messwerk=k.messwerk, instanz=kn.kennung + ":ende", knoten_ziel=None, werte={"fenster_ende": True}))
    return aus


@baustein("einbettung_andrang", "ausloeser", "Andrang bei der Einbettung",
          "Je Einbettungsmodell und Rechner ein Lauf, wenn Einbettungsaufträge länger als die Andrangsschwelle (Regelwerk) auf eine freie Instanz warten.")
def einbettung_andrang(k: Kontext) -> list[Kontext]:
    gruppen: dict[tuple[str, str], list[Auftrag]] = {}
    for a in k.verbund.wartende_auftraege():
        if (a.faehigkeit == Faehigkeit.EINBETTUNG and a.zustand == Auftragszustand.EINGEREIHT and a.wartet_auf_familie and a.wartet_auf_knoten
                and k.verbund.zeit_s - a.eingang_s >= k.r.einbettung_andrang_s):
            gruppen.setdefault((a.wartet_auf_familie, a.wartet_auf_knoten), []).append(a)
    return [Kontext(verbund=k.verbund, messwerk=k.messwerk, instanz=f"{fam}@{knoten}", knoten_quelle=knoten,
                    werte={"familie": fam, "wartende": len(liste), "auftraege": [a.kennung for a in liste]})
            for (fam, knoten), liste in gruppen.items()]


def _gebremst(v: Verbund, knoten: str | None) -> Hintergrundstufe | None:
    """Die Stufe des Hintergrunds auf dem Rechner, wenn sie nicht frei ist (Regel "Hintergrund bei Rechnerlast")."""
    kn = v.knoten.get(knoten) if knoten else None
    return kn.hintergrund_stufe if kn is not None and kn.hintergrund_stufe != Hintergrundstufe.FREI else None


@baustein("einbettung_ruhe", "ausloeser", "Ruhe bei der Einbettung",
          "Je Einbettungsmodell und Rechner ein Lauf, wenn weitere Instanzen länger als die Ruhezeit (Regelwerk) nichts zu tun hatten und kein Einbettungsauftrag wartet. "
          "Ist der Hintergrund des Rechners gedrosselt oder angehalten, sofort, und wartender Hintergrund zählt nicht.")
def einbettung_ruhe(k: Kontext) -> list[Kontext]:
    v = k.verbund
    gruppen: dict[tuple[str, str], list[Modell]] = {}
    for m in v.modelle.values():
        knoten = v.dienste[m.dienst].knoten
        gebremst = _gebremst(v, knoten)
        if (not m.zusatz or Faehigkeit.EINBETTUNG not in m.faehigkeiten or knoten is None or m.zustand != Modellzustand.GELADEN or v.belegung(m.kennung)
                or (not gebremst and m.letzte_nutzung_s is not None and v.zeit_s - m.letzte_nutzung_s < k.r.einbettung_ruhe_s)):
            continue
        if any(a.faehigkeit == Faehigkeit.EINBETTUNG and (not gebremst or wirksame_prioritaet(v, a) > int(Prioritaet.HINTERGRUND))
               for a in v.wartende_auf_familie(m.familie)):
            continue
        gruppen.setdefault((m.familie, knoten), []).append(m)
    aus = []
    for (fam, knoten), liste in gruppen.items():
        gebremst = _gebremst(v, knoten)
        anlass = f"Hintergrund {gebremst.value}, kein Auftrag" if gebremst else f"{k.r.einbettung_ruhe_s:.0f} s ohne Arbeit"
        aus.append(Kontext(verbund=v, messwerk=k.messwerk, instanz=f"{fam}@{knoten}", knoten_quelle=knoten, knoten_ziel=knoten,
                           modelle_entladen=[m.kennung for m in liste], aufwand_s=k.messwerk.entladezeit_s,
                           werte={"familie": fam, "anzahl": len(liste), "anlass": anlass}))
    return aus


@baustein("laeufer_arbeitet_ohne_auftrag", "ausloeser", "Läufer arbeitet ohne Auftrag",
          "Je Arbeiter des Modell-Läufers eines wachen Rechners ein Lauf, wenn er seit der Frist (Regelwerk) in jeder Messung mindestens die Schwelle "
          "rechnet und in diesem Fenster kein Auftrag der Leitstelle auf dem Läufer lief, zugeteilt war oder geladen wurde; nicht mehr, sobald er beendet wird.")
def laeufer_arbeitet_ohne_auftrag(k: Kontext) -> list[Kontext]:
    v = k.verbund
    aus = []
    for kn in sorted(v.knoten.values(), key=lambda x: x.kennung):
        if kn.schlaeft:
            continue
        for p in ohne_auftrag(v, kn):
            if p.beenden_s is not None:
                continue
            seit = ohne_auftrag_seit(v, kn.kennung, p)
            seit = v.zeit_s if seit is None else seit
            aus.append(Kontext(verbund=v, messwerk=k.messwerk, instanz=f"{p.pid}@{kn.kennung}", knoten_quelle=kn.kennung, knoten_ziel=kn.kennung,
                               werte={"pid": p.pid, "prozess": p.name, "modelldatei": datei(p.modelldatei), "pfad": p.modelldatei, "dauer": dauer(v.zeit_s - seit),
                                      "kerne": kerne(p.cpu_prozent)}))
    return aus


@baustein("rechnerlast", "ausloeser", "Rechnerlast",
          "Je wachem Rechner mit Lastmessung ein Lauf je Takt, mit der Fremdlast im gleitenden Mittel über die Frist (Regelwerk). Ohne frische Messung "
          "nur, solange sein Hintergrund nicht frei ist (dann geben die Prüfungen ihn frei).")
def rechnerlast(k: Kontext) -> list[Kontext]:
    v = k.verbund
    aus = []
    for kn in sorted(v.knoten.values(), key=lambda x: x.kennung):
        if kn.schlaeft:
            continue
        mittel = fremd_mittel(v, kn)
        if mittel is None and kn.hintergrund_stufe == Hintergrundstufe.FREI:
            continue
        aus.append(Kontext(verbund=v, messwerk=k.messwerk, instanz=kn.kennung, knoten_quelle=kn.kennung, knoten_ziel=kn.kennung,
                           werte={"mittel": mittel, "last": prozent(mittel) if mittel is not None else "nicht gemessen",
                                  "vorher": kn.hintergrund_stufe.value, "frist": f"{k.r.last_frist_s:.0f} s"}))
    return aus


@baustein("modell_doppelt_geladen", "ausloeser", "Modell doppelt im Speicher", "Dieselbe Modellfamilie liegt auf zwei wachen Knoten im Speicher.")
def modell_doppelt_geladen(k: Kontext) -> list[Kontext]:
    """Eine Kopie auf einem schlafenden Rechner zählt nicht: sonst wiche womöglich die nutzbare auf dem wachen."""
    aus = []
    familien: dict[str, list[Modell]] = {}
    for m in k.verbund.modelle.values():
        if m.im_speicher and not k.verbund.dienste[m.dienst].extern and not k.verbund.auf_schlafendem(m.dienst):
            familien.setdefault(m.familie, []).append(m)
    for fam, liste in familien.items():
        knoten = {k.verbund.dienste[m.dienst].knoten for m in liste}
        if len(knoten) >= 2:
            aus.append(Kontext(verbund=k.verbund, messwerk=k.messwerk, instanz=fam, werte={"familie": fam, "instanzen": [m.kennung for m in liste]}))
    return aus


@baustein("lage_wechsel", "ausloeser", "Lage wechselt", "Ein Lauf je Takt mit der aktuellen Lage; die Aktionen prüfen selbst, ob etwas zu tun ist.")
def lage_wechsel(k: Kontext) -> list[Kontext]:
    lage, grund = lagebeurteilung.beurteilen(k.verbund)
    return [Kontext(verbund=k.verbund, messwerk=k.messwerk, instanz=lage.value, lage=lage, werte={"grund": grund})]


# ── Prüfungen ────────────────────────────────────────────────────────────

@baustein("anderer_knoten_mit_platz", "pruefung", "Anderer Knoten mit Platz?", "Gibt es einen anderen erlaubten Knoten, auf dem das Modell ohne Entladen passt (Dienst darf auch installiert, aber aus sein)?", reserve_gb=2.0)
def anderer_knoten_mit_platz(k: Kontext, reserve_gb: float = 2.0) -> bool:
    a = k.auftrag
    assert a is not None
    fam = a.wartet_auf_familie or k.verbund.erste_familie(a)
    if not fam:
        return False
    beste: tuple[float, Modell, str] | None = None
    for m in k.verbund.modelle.values():
        if m.familie != fam or a.faehigkeit not in m.faehigkeiten:
            continue
        d = k.verbund.dienste[m.dienst]
        if d.extern or d.knoten is None or d.knoten == k.knoten_quelle:
            continue
        if d.zustand not in (Dienstzustand.BEREIT, Dienstzustand.AUS) or (d.zustand == Dienstzustand.AUS and not d.installiert):
            continue
        if not erlaubte_zone(k.verbund, a, d.knoten) or hintergrund_gebremst(k.verbund, a, m):
            continue
        if m.im_speicher or not m.ladbar(k.verbund.zeit_s):
            continue
        plan = planen(k.verbund, d.knoten, m.gb + reserve_gb, k.messwerk, familie=fam)
        if not plan.passt or plan.entladen:
            continue
        aufwand = k.messwerk.ladezeit(fam, d.knoten, m.gb).sekunden
        if d.zustand == Dienstzustand.AUS:
            aufwand += k.messwerk.startzeit(d.kennung, d.startzeit_s).sekunden
        if beste is None or aufwand < beste[0]:
            beste = (aufwand, m, d.kennung)
    if beste is None:
        k.werte["platz"] = "kein anderer Knoten mit Platz in einer erlaubten Zone"
        return False
    aufwand, m, dienst = beste
    k.knoten_ziel = k.verbund.dienste[dienst].knoten
    k.dienst_ziel = dienst
    k.modell_ziel = m.kennung
    k.aufwand_s = aufwand
    k.werte["platz"] = f"{k.verbund.knoten[k.knoten_ziel].name}: {komma(k.verbund.frei_gb(k.knoten_ziel))} GB frei"
    return True


@baustein("dienst_dort_laeuft", "pruefung", "Dienst dort läuft?", "Ist der Dienst auf dem Zielknoten bereit?")
def dienst_dort_laeuft(k: Kontext) -> bool:
    return bool(k.dienst_ziel) and k.verbund.dienste[k.dienst_ziel].zustand == Dienstzustand.BEREIT


@baustein("dienst_installiert", "pruefung", "Dienst installiert?", "Ist der Dienst auf dem Zielknoten installiert und nur nicht gestartet?")
def dienst_installiert(k: Kontext) -> bool:
    return bool(k.dienst_ziel) and k.verbund.dienste[k.dienst_ziel].installiert and k.verbund.dienste[k.dienst_ziel].zustand == Dienstzustand.AUS


@baustein("gewinn_gegen_aufwand", "pruefung", "Gewinn gegen Aufwand?", "Spart die Maßnahme mindestens das Faktor-fache ihres gemessenen Aufwands an Wartezeit?", faktor=None)
def gewinn_gegen_aufwand(k: Kontext, faktor: float | None = None) -> bool:
    f = k.r.gewinnfaktor if faktor is None else faktor
    if k.auftrag is not None and k.gewinn_s == 0.0:
        k.gewinn_s = erwartete_wartezeit(k, k.auftrag)
    k.werte["gewinn"] = f"{k.gewinn_s:.0f} s"
    k.werte["aufwand"] = f"{k.aufwand_s:.0f} s"
    k.werte["faktor"] = f"{f:g}"
    return k.gewinn_s >= f * k.aufwand_s and k.gewinn_s > 0


@baustein("leerlaufmodell_vorhanden", "pruefung", "Leerlaufmodell auf dem Knoten?", "Belegt auf dem Knoten des wartenden Auftrags ein ungenutztes, nicht geschütztes Modell den Platz, und reicht der Platz nach dem Entladen?")
def leerlaufmodell_vorhanden(k: Kontext) -> bool:
    a = k.auftrag
    assert a is not None and k.knoten_quelle
    fam = a.wartet_auf_familie or k.verbund.erste_familie(a)
    m = instanz_der_familie(k.verbund, fam, a.faehigkeit, k.knoten_quelle) if fam else None
    if m is None or m.im_speicher:
        return False
    if not m.ladbar(k.verbund.zeit_s):
        k.werte["leerlauf"] = f"Laden von {m.name} ist gesperrt: {m.ladesperre_grund}"
        return False
    plan = planen(k.verbund, k.knoten_quelle, m.gb, k.messwerk, familie=fam, nur_leerlauf=True, leerlauf_grenze_s=k.r.bedarfsfrist_s,
                  fuer_arbeit=a.arbeit)
    if not plan.passt or not plan.entladen:
        k.werte["leerlauf"] = plan.begruendung
        return False
    k.modelle_entladen = plan.entladen
    k.modell_ziel = m.kennung
    k.knoten_ziel = k.knoten_quelle
    k.dienst_ziel = m.dienst
    k.aufwand_s = plan.aufwand_s
    # Gewinn: so lange würde der Auftrag ohne das Räumen warten (bis ein rechnendes Modell fertig ist; sonst unbestimmt lange)
    fristen = [max(k.messwerk.rest_s(x.anwendung, x.faehigkeit.value, x.fortschritt_s) for x in k.verbund.belegung(b.kennung))
               for b in k.verbund.modelle_auf(k.knoten_quelle) if b.im_speicher and k.verbund.belegung(b.kennung) and not b.geschuetzt(k.r.schutzgrenze_mrd)]
    k.gewinn_s = min(fristen) if fristen else 3600.0
    k.werte["leerlauf"] = plan.begruendung
    return True


@baustein("platz_ohne_entladen", "pruefung", "Platz ohne Entladen?", "Gibt es einen erlaubten Knoten, auf dem das Modell jetzt ohne Entladen passt und danach noch Reserve bleibt?", reserve_anteil=0.05)
def platz_ohne_entladen(k: Kontext, reserve_anteil: float = 0.05) -> bool:
    a = k.auftrag
    assert a is not None
    fam = k.verbund.erste_familie(a)
    if not fam:
        return False
    for m in k.verbund.modelle.values():
        if m.familie != fam or a.faehigkeit not in m.faehigkeiten or m.im_speicher:
            continue
        d = k.verbund.dienste[m.dienst]
        if (d.extern or d.knoten is None or not d.nutzbar or not erlaubte_zone(k.verbund, a, d.knoten) or not m.ladbar(k.verbund.zeit_s)
                or hintergrund_gebremst(k.verbund, a, m)):
            continue
        budget = k.verbund.knoten[d.knoten].budget_gb(k.r.budget_reserve_gb)
        plan = planen(k.verbund, d.knoten, m.gb + budget * reserve_anteil, k.messwerk, familie=fam)
        if plan.passt and not plan.entladen:
            k.knoten_ziel, k.dienst_ziel, k.modell_ziel = d.knoten, d.kennung, m.kennung
            k.aufwand_s = k.messwerk.ladezeit(fam, d.knoten, m.gb).sekunden
            k.gewinn_s = k.aufwand_s
            k.werte["platz"] = f"{k.verbund.knoten[d.knoten].name}: {komma(k.verbund.frei_gb(d.knoten))} GB frei"
            return True
    return False


@baustein("weitere_instanz_moeglich", "pruefung", "Weitere Instanz möglich?", "Wartet der Auftrag auf eine freie Instanz eines Dienstes, der mehrere Instanzen erlaubt, ist die Höchstzahl nicht erreicht, startet keine gerade, und passt eine weitere ohne Entladen?", reserve_gb=1.0)
def weitere_instanz_moeglich(k: Kontext, reserve_gb: float = 1.0) -> bool:
    a = k.auftrag
    assert a is not None
    fam = a.wartet_auf_familie
    if not fam or a.zustand != Auftragszustand.EINGEREIHT:
        return False
    alle = k.verbund.instanzen(fam, a.wartet_auf_knoten)
    grund = next((m for m in alle if not m.zusatz), None)
    if grund is None or grund.instanzen_hoechstens <= 1:
        k.werte["instanz"] = "der Dienst erlaubt nur eine Instanz"
        return False
    if len(alle) >= grund.instanzen_hoechstens:
        k.werte["instanz"] = f"alle {grund.instanzen_hoechstens} Instanzen laufen"
        return False
    if any(m.zustand == Modellzustand.LAEDT for m in alle):
        k.werte["instanz"] = "eine Instanz startet gerade"
        return False
    d = k.verbund.dienste[grund.dienst]
    if d.extern or d.knoten is None or not d.nutzbar:
        return False
    if (stufe := _gebremst(k.verbund, d.knoten)) and wirksame_prioritaet(k.verbund, a) == int(Prioritaet.HINTERGRUND):
        k.werte["instanz"] = f"Hintergrund auf {k.verbund.knoten[d.knoten].name} {stufe.value}: keine weitere Instanz für Hintergrund"
        return False
    plan = planen(k.verbund, d.knoten, grund.gb + reserve_gb, k.messwerk, familie=fam)
    if not plan.passt or plan.entladen:
        k.werte["instanz"] = plan.begruendung
        return False
    k.dienst_ziel, k.knoten_ziel, k.modell_ziel = d.kennung, d.knoten, grund.kennung
    k.werte |= {"familie": fam, "anzahl": 1, "instanz": f"Instanz {len(alle) + 1} von höchstens {grund.instanzen_hoechstens}"}
    k.aufwand_s = k.messwerk.ladezeit(fam, d.knoten, grund.gb).sekunden
    return True


def gespraechsmodelle(verbund: Verbund) -> frozenset[str]:
    """Familien, die eine Anwendung für Text in ihrer Kette hat: sie weichen nie für weitere Einbettungsinstanzen (ein
    Gespräch soll nicht auf das Neuladen warten, weil die Einbettung schneller sein wollte)."""
    return frozenset(fam for app in verbund.anwendungen.values() for fam in app.ketten.get(Faehigkeit.TEXT, []))


@baustein("einbettungsinstanzen_moeglich", "pruefung", "Weitere Einbettungsinstanzen möglich?",
          "Wie viele weitere Instanzen des Einbettungsmodells fehlen (Wartende ohne ladende Instanz), erlaubt der Dienst (Höchstzahl), "
          "und passen sie mit dem Spielraum des Dienstes ins Budget des Rechners? Dafür dürfen ungenutzte Modelle weichen, kleinste zuerst; "
          "nie Gesprächsmodelle der Anwendungen, nie Modelle, die in der Schonfrist (Regelwerk) genutzt wurden.")
def einbettungsinstanzen_moeglich(k: Kontext) -> bool:
    v, fam, knoten = k.verbund, k.werte["familie"], k.knoten_quelle
    alle = [m for m in v.instanzen(fam, knoten) if not m.zusatz or m.im_speicher]   # entladene weitere zählen nicht mehr
    grund = next((m for m in alle if not m.zusatz), None)
    if grund is None or grund.instanzen_hoechstens <= 1:
        k.werte["instanz"] = "der Dienst erlaubt nur eine Instanz"
        return False
    d = v.dienste[grund.dienst]
    if d.extern or not d.nutzbar or not grund.im_speicher:
        k.werte["instanz"] = "die Grundinstanz ist nicht bereit"
        return False
    wartende = k.werte["wartende"]
    if stufe := _gebremst(v, knoten):
        vorn = [x for x in k.werte["auftraege"] if x in v.auftraege and wirksame_prioritaet(v, v.auftraege[x]) > int(Prioritaet.HINTERGRUND)]
        if not vorn:
            k.werte["instanz"] = f"Hintergrund auf {v.knoten[knoten].name} {stufe.value}: es wartet nur Hintergrund"
            return False
        wartende = len(vorn)
    ladend = sum(1 for m in alle if m.zustand == Modellzustand.LAEDT)
    anzahl = min(wartende - ladend, grund.instanzen_hoechstens - len(alle))
    if anzahl <= 0:
        k.werte["instanz"] = (f"alle {grund.instanzen_hoechstens} Instanzen laufen" if len(alle) >= grund.instanzen_hoechstens
                              else f"{ladend} Instanzen laden schon")
        return False
    verschont = gespraechsmodelle(v) | {fam}
    while anzahl > 0:
        plan = planen(v, knoten, anzahl * grund.gb + d.einbettung_spielraum_gb, k.messwerk, familie=fam, nur_leerlauf=True,
                      leerlauf_grenze_s=k.r.einbettung_schonfrist_s, verschont=verschont, kleinste_zuerst=True)
        if plan.passt:
            break
        anzahl -= 1
    if anzahl <= 0:
        k.werte["instanz"] = f"kein Platz mit {komma(d.einbettung_spielraum_gb)} GB Spielraum: {plan.begruendung}"
        return False
    k.dienst_ziel, k.knoten_ziel, k.modell_ziel = d.kennung, knoten, grund.kennung
    k.modelle_entladen = list(plan.entladen)
    k.aufwand_s = plan.aufwand_s
    k.gewinn_s = sum(erwartete_wartezeit(k, v.auftraege[a]) for a in k.werte["auftraege"] if a in v.auftraege)
    k.werte |= {"anzahl": anzahl, "instanz": f"{anzahl} weitere, dann {len(alle) + anzahl} von höchstens {grund.instanzen_hoechstens}",
                "platz": plan.begruendung}
    return True


@baustein("muss_entladen", "pruefung", "Muss etwas weichen?", "Hat der Plan Modelle vorgemerkt, die vorher weichen müssen?")
def muss_entladen(k: Kontext) -> bool:
    return bool(k.modelle_entladen)


@baustein("kette_hat_alternative", "pruefung", "Kette hat geladene Alternative?", "Ist ein anderes Modell der Kette des Auftrags auf einem erlaubten Knoten geladen und frei?")
def kette_hat_alternative(k: Kontext) -> bool:
    a = k.auftrag
    assert a is not None
    if a.festes_modell:
        return False
    kette = k.verbund.kette(a)
    for fam in kette:
        if fam == a.wartet_auf_familie:
            continue
        for m in k.verbund.modelle.values():
            if m.familie != fam or a.faehigkeit not in m.faehigkeiten or m.zustand not in (Modellzustand.GELADEN, Modellzustand.RECHNET):
                continue
            d = k.verbund.dienste[m.dienst]
            if d.extern or d.knoten is None or not d.nutzbar or not erlaubte_zone(k.verbund, a, d.knoten) or hintergrund_gebremst(k.verbund, a, m):
                continue
            if len(k.verbund.belegung(m.kennung)) >= k.verbund.plaetze(m) or k.verbund.anfrage_frei_in_s(m.dienst) > 0:
                continue
            k.knoten_ziel, k.dienst_ziel, k.modell_ziel = d.knoten, d.kennung, m.kennung
            k.aufwand_s = 0.0
            k.gewinn_s = erwartete_wartezeit(k, a)
            k.werte["alternative"] = m.name
            return True
    return False


@baustein("anwendung_darf_extern", "pruefung", "Anwendung darf extern?", "Erlaubt die Leitstelle der Anwendung die Zone extern, und nennt die Anfrage externe Modelle auf ihrer Erlaubnisliste?")
def anwendung_darf_extern(k: Kontext) -> bool:
    a = k.auftrag
    assert a is not None
    app = k.verbund.anwendungen[a.anwendung]
    return app.extern_erlaubt and Zone.EXTERN in app.zonen and bool(a.extern_familien)


@baustein("wartezeit_ueber_schwelle", "pruefung", "Wartezeit über der Schwelle?", "Liegt die erwartete Wartezeit über der eingestellten Grenze für das Ausweichen?", schwelle_s=None)
def wartezeit_ueber_schwelle(k: Kontext, schwelle_s: float | None = None) -> bool:
    a = k.auftrag
    assert a is not None
    s = k.r.extern_schwelle_s if schwelle_s is None else schwelle_s
    k.gewinn_s = erwartete_wartezeit(k, a)
    k.werte["wartezeit"] = f"{k.gewinn_s:.0f} s"
    return k.gewinn_s >= s


@baustein("extern_dienst_vorhanden", "pruefung", "Externer Dienst mit dieser Fähigkeit?", "Gibt es einen externen Anbieter, der die Fähigkeit und möglichst die Kette bedient?")
def extern_dienst_vorhanden(k: Kontext) -> bool:
    a = k.auftrag
    assert a is not None
    kette = k.verbund.kette(a)
    treffer = []
    for m in k.verbund.modelle.values():
        d = k.verbund.dienste[m.dienst]
        if (d.extern and d.nutzbar and a.faehigkeit in m.faehigkeiten and a.faehigkeit in d.faehigkeiten and k.verbund.extern_erlaubt(a, m)
                and k.verbund.anfrage_frei_in_s(d.kennung) == 0):
            rang = kette.index(m.familie) if m.familie in kette else len(kette)
            treffer.append((rang, m, d))
    if not treffer:
        return False
    _, m, d = sorted(treffer, key=lambda t: t[0])[0]
    k.dienst_ziel, k.modell_ziel, k.knoten_ziel = d.kennung, m.kennung, None
    k.aufwand_s = 0.0
    return True


@baustein("eine_kopie_ungenutzt", "pruefung", "Eine Kopie ungenutzt?", "Ist eine der Kopien ohne Auftrag, ohne wartenden Bedarf und über die Mindestverweildauer hinaus?")
def eine_kopie_ungenutzt(k: Kontext) -> bool:
    """Sammelt alle Kopien, die weichen dürfen (geladen, ungeschützt, ohne Aufträge, ohne Wartende derselben Familie, Verweildauer um).
    Die erste wird vorgemerkt; die Prüfung "Bedarf auf diesem Knoten?" wählt danach die Kopie, auf deren Knoten jemand wartet."""
    frei: list[str] = []
    for kennung in k.werte.get("instanzen", []):
        m = k.verbund.modelle[kennung]
        if m.zustand != Modellzustand.GELADEN or m.geschuetzt(k.r.schutzgrenze_mrd) or k.verbund.belegung(m.kennung):
            continue
        knoten = k.verbund.dienste[m.dienst].knoten
        if any(a.wartet_auf_knoten == knoten and (a.wartet_auf_familie == m.familie) for a in k.verbund.wartende_auftraege()):
            continue
        if m.geladen_seit_s is not None and k.verbund.zeit_s - m.geladen_seit_s < k.r.mindestverweildauer_s:
            continue
        frei.append(m.kennung)
    if not frei:
        return False
    k.werte["ungenutzt"] = frei
    _kopie_waehlen(k, frei[0])
    return True


def _kopie_waehlen(k: Kontext, kennung: str) -> None:
    m = k.verbund.modelle[kennung]
    k.modelle_entladen = [m.kennung]
    k.knoten_quelle = k.knoten_ziel = k.verbund.dienste[m.dienst].knoten
    k.aufwand_s = k.messwerk.entladezeit_s


@baustein("bedarf_anderswo", "pruefung", "Bedarf auf diesem Knoten?", "Wartet auf dem Knoten einer ungenutzten Kopie ein Auftrag auf Speicher? Dann weicht genau diese Kopie.")
def bedarf_anderswo(k: Kontext) -> bool:
    for kennung in k.werte.get("ungenutzt", [k.modelle_entladen[0]] if k.modelle_entladen else []):
        knoten = k.verbund.dienste[k.verbund.modelle[kennung].dienst].knoten
        wartende = [a for a in k.verbund.wartende_auftraege() if a.zustand == Auftragszustand.WARTET_SPEICHER and a.wartet_auf_knoten == knoten]
        if wartende:
            _kopie_waehlen(k, kennung)
            k.gewinn_s = max(erwartete_wartezeit(k, a) for a in wartende)
            k.werte["bedarf"] = ", ".join(a.kennung for a in wartende)
            return True
    return False


@baustein("hintergrund_auftraege_vorhanden", "pruefung", "Hintergrundaufträge vorhanden?", "Gibt es offene Aufträge der Stufe Hintergrund?")
def hintergrund_auftraege_vorhanden(k: Kontext) -> bool:
    return any(a.prioritaet == Prioritaet.HINTERGRUND for a in k.verbund.offene_auftraege())


@baustein("lage_ist", "pruefung", "Lage ist?", "Entspricht die Lage dem Parameter?", lage="angespannt")
def lage_ist(k: Kontext, lage: str = "angespannt") -> bool:
    return k.lage is not None and k.lage.value == lage


@baustein("hintergrund_angehalten", "pruefung", "Hintergrund angehalten?", "Ist der Hintergrund gerade angehalten?")
def hintergrund_angehalten(k: Kontext) -> bool:
    return not k.verbund.hintergrund_an


@baustein("umgehung_am_laeufer", "pruefung", "Umgehung am Läufer?",
          "Spricht ein Programm den Läufer dieses Rechners am Leitstand vorbei an (nach der Deutung, nicht die Leitstelle selbst auf dem direkten Weg)? "
          "Dann rechnet der Arbeiter vermutlich für diesen Kunden.")
def umgehung_am_laeufer(k: Kontext) -> bool:
    wer = k.verbund.knoten[k.knoten_quelle].laeufer_umgehungen if k.knoten_quelle else []
    if wer:
        k.werte["wer"] = ", ".join(wer)
    return bool(wer)


@baustein("last_ueber_grenze", "pruefung", "Fremdlast über der Grenze?",
          "Liegt die Fremdlast im Mittel mindestens bei der Grenze zum Drosseln oder Anhalten (Parameter; Werte im Regelwerk)? Gilt die Stufe schon, "
          "heißt es erst unter der Grenze minus Abstand nein (gegen Flattern). Ohne Messung nein.", grenze="drosseln")
def last_ueber_grenze(k: Kontext, grenze: str = "drosseln") -> bool:
    r, kn = k.r, k.verbund.knoten[k.knoten_quelle or ""]
    stufe, wert = ((Hintergrundstufe.ANGEHALTEN, r.last_anhalten_ab_prozent) if grenze == "anhalten"
                   else (Hintergrundstufe.GEDROSSELT, r.last_drosseln_ab_prozent))
    if STUFENRANG[kn.hintergrund_stufe] >= STUFENRANG[stufe]:
        wert -= r.last_abstand_prozent
    k.werte[f"grenze_{grenze}"] = prozent(wert)
    mittel = k.werte.get("mittel")
    return mittel is not None and mittel >= wert


@baustein("stufe_ist", "pruefung", "Hintergrund hat die Stufe?", "Hat der Hintergrund des Rechners die Stufe des Parameters (frei, gedrosselt, angehalten)?",
          stufe="frei")
def stufe_ist(k: Kontext, stufe: str = "frei") -> bool:
    return k.verbund.knoten[k.knoten_quelle or ""].hintergrund_stufe.value == stufe


@baustein("immer", "pruefung", "Immer", "Prüfung, die immer ja sagt (für Vorlagen ohne Bedingung).")
def immer(k: Kontext) -> bool:
    return True


# ── Aktionen: beschreiben nur, ausgeführt wird im Vollzug ─────────────────

@baustein("dienst_starten", "aktion", "Dienst starten", "Startet den Dienst auf dem Zielknoten über dessen Maschinenraum.")
def dienst_starten(k: Kontext) -> dict[str, Any]:
    return {"dienst": k.dienst_ziel}


@baustein("modell_laden", "aktion", "Modell laden", "Lädt das Zielmodell auf dem Zielknoten.")
def modell_laden(k: Kontext) -> dict[str, Any]:
    return {"modell": k.modell_ziel}


@baustein("modell_entladen", "aktion", "Modell entladen", "Entlädt die geplanten Modelle.")
def modell_entladen(k: Kontext) -> dict[str, Any]:
    return {"modelle": list(k.modelle_entladen)}


@baustein("instanz_starten", "aktion", "Weitere Instanz starten", "Startet weitere Instanzen (so viele, wie die Prüfung ermittelt hat) des Modells oder Dienstes, auf den gewartet wird.")
def instanz_starten(k: Kontext) -> dict[str, Any]:
    return {"dienst": k.dienst_ziel, "familie": k.werte.get("familie"), "vorbild": k.modell_ziel, "anzahl": int(k.werte.get("anzahl", 1))}


@baustein("auftrag_umleiten", "aktion", "Auftrag umleiten", "Teilt den Auftrag dem Zieldienst und Zielmodell zu.")
def auftrag_umleiten(k: Kontext) -> dict[str, Any]:
    return {"auftrag": k.auftrag.kennung if k.auftrag else None, "dienst": k.dienst_ziel, "modell": k.modell_ziel, "knoten": k.knoten_ziel}


@baustein("auftrag_extern", "aktion", "Extern rechnen", "Gibt den Auftrag an den externen Anbieter.")
def auftrag_extern(k: Kontext) -> dict[str, Any]:
    return {"auftrag": k.auftrag.kennung if k.auftrag else None, "dienst": k.dienst_ziel, "modell": k.modell_ziel}


@baustein("melden", "aktion", "Melden", "Schreibt die Maßnahme mit Begründung in Meldungen und Protokoll.", text="")
def melden(k: Kontext, text: str = "") -> dict[str, Any]:
    return {"text": text}


@baustein("signal_senden", "aktion", "Signal senden", "Schickt der Anwendung des Auftrags ein Signal.", signalart="signal.modell")
def signal_senden(k: Kontext, signalart: str = "signal.modell") -> dict[str, Any]:
    return {"anwendung": k.auftrag.anwendung if k.auftrag else None, "art": signalart}


@baustein("laufende_abbrechen_mit_teilergebnis", "aktion", "Laufende abbrechen, Teilergebnis melden", "Bricht laufende Aufträge auf dem ausgefallenen Knoten ab und liefert das bisher Erzeugte.")
def laufende_abbrechen_mit_teilergebnis(k: Kontext) -> dict[str, Any]:
    return {"knoten": k.knoten_quelle}


@baustein("wartende_neu_einreihen", "aktion", "Wartende neu einreihen", "Nimmt wartenden Aufträgen des ausgefallenen Knotens die Zuteilung, damit der Zuteiler neu entscheidet.")
def wartende_neu_einreihen(k: Kontext) -> dict[str, Any]:
    return {"knoten": k.knoten_quelle}


@baustein("bevorzugten_knoten_setzen", "aktion", "Bevorzugten Knoten für Hintergrund setzen", "Hintergrundarbeit läuft bevorzugt auf dem Zielknoten (leer: keine Bevorzugung).")
def bevorzugten_knoten_setzen(k: Kontext) -> dict[str, Any]:
    return {"knoten": k.knoten_ziel}


@baustein("hintergrund_anhalten", "aktion", "Hintergrund anhalten", "Hält Hintergrundaufträge an, interaktive laufen weiter.")
def hintergrund_anhalten(k: Kontext) -> dict[str, Any]:
    return {"an": False}


@baustein("hintergrund_fortsetzen", "aktion", "Hintergrund fortsetzen", "Lässt Hintergrundaufträge wieder laufen.")
def hintergrund_fortsetzen(k: Kontext) -> dict[str, Any]:
    return {"an": True}


@baustein("laeufer_prozess_beenden", "aktion", "Prozess des Läufers beenden",
          "Lässt den Arbeiter vom Maschinenraum seines Rechners beenden (erst freundlich, dann hart); der Maschinenraum prüft vorher selbst, dass er "
          "ein Arbeiter des Läufers ist, und beendet nie den Hauptprozess. Der Läufer lädt das Modell bei Bedarf neu.")
def laeufer_prozess_beenden(k: Kontext) -> dict[str, Any]:
    return {"knoten": k.knoten_quelle, "pid": k.werte["pid"], "pfad": k.werte["pfad"]}


def _stufe_setzen(k: Kontext, stufe: Hintergrundstufe, grund: str) -> dict[str, Any]:
    return {"knoten": k.knoten_quelle, "stufe": stufe.value, "grund": grund}


@baustein("hintergrund_drosseln", "aktion", "Hintergrund drosseln",
          "Hintergrundaufträge bekommen auf dem Rechner nur noch die Grundinstanz einer Familie, keine weitere; weitere Instanzen ohne Auftrag weichen sofort.")
def hintergrund_drosseln(k: Kontext) -> dict[str, Any]:
    return _stufe_setzen(k, Hintergrundstufe.GEDROSSELT, f"Fremdlast {k.werte['last']}, drosseln ab {k.werte.get('grenze_drosseln', '-')}")


@baustein("hintergrund_auf_knoten_anhalten", "aktion", "Hintergrund auf dem Rechner anhalten",
          "Hintergrundaufträge werden auf dem Rechner nicht mehr zugeteilt, auch nicht nach der Fairness-Frist; laufende rechnen zu Ende.")
def hintergrund_auf_knoten_anhalten(k: Kontext) -> dict[str, Any]:
    return _stufe_setzen(k, Hintergrundstufe.ANGEHALTEN, f"Fremdlast {k.werte['last']}, anhalten ab {k.werte.get('grenze_anhalten', '-')}")


@baustein("hintergrund_auf_knoten_freigeben", "aktion", "Hintergrund auf dem Rechner freigeben", "Hintergrund darf auf dem Rechner wieder alles.")
def hintergrund_auf_knoten_freigeben(k: Kontext) -> dict[str, Any]:
    grund = (f"Fremdlast {k.werte['last']}, frei unter {k.werte.get('grenze_drosseln', '-')}" if k.werte.get("mittel") is not None
             else "Fremdlast nicht mehr gemessen")
    return _stufe_setzen(k, Hintergrundstufe.FREI, grund)
