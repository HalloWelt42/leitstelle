"""Zuteiler: welcher Dienst, welches Modell, welcher Knoten für einen wartenden Auftrag.

Reihenfolge der Prüfung (ARCHITEKTUR 5.1): Rechte der Anwendung, Modellwahl der Anwendung, Speicher, Plätze,
Priorität mit Fairness, Direktweg. Jede Entscheidung trägt eine Begründung in Worten. Arbeit "nur bei Ruhe" (Regelwerk)
kommt zuletzt und nur, wenn keine andere Arbeit offen ist und die Ruhezeit seit der letzten vorbei ist; sonst wartet sie
im Zustand `wartet_ruhe`. Hintergrund folgt dazu der Stufe
jedes Rechners nach seiner Fremdlast (ZUSAMMENSPIEL Z6): gedrosselt nur die Grundinstanz, angehalten nichts.
Der Zuteiler lädt nicht selbst; er sagt, was zu laden wäre (Zuteilung mit laden=True), das
Ausführen übernimmt der Vollzug (Dienst-Adapter, im Test der Schein-Verbund).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .fenster import Bedarf
from .messungen import Messwerk
from .modelle import Auftrag, Modell, Verbund
from .speicherplaner import planen
from .werte import Auftragszustand, Betriebsmodus, Hintergrundstufe, Modellzustand, Prioritaet, Zone
from .text import komma, schlaf_satz


#: Ablehnung eines Auftrags ohne Modell (Grund `modell_fehlt`): das Modell wählt immer die Anwendung (Nutzer 07.11.2026)
MODELL_FEHLT = "Die Anwendung muss ihr Modell nennen; die Leitstelle wählt keins."


class Zuteilung(BaseModel):
    auftrag: str
    dienst: str
    knoten: str | None
    modell: str
    laden: bool
    direkt: bool
    begruendung: str


class Wartegrund(BaseModel):
    auftrag: str
    zustand: Auftragszustand
    begruendung: str
    grund: str | None = None          # Wort für Ablehnungen (PROTOKOLL.md Abschnitt 7)
    wartet_auf_familie: str | None = None
    wartet_auf_knoten: str | None = None
    schlafende_knoten: list[str] = Field(default_factory=list)   # rechner_schlaeft: auf diese Rechner wartet der Auftrag
    voraussichtlich_s: float | None = None


class Zuteilergebnis(BaseModel):
    zuteilungen: list[Zuteilung] = Field(default_factory=list)
    wartend: list[Wartegrund] = Field(default_factory=list)
    abgelehnt: list[Wartegrund] = Field(default_factory=list)


def zone_passt(verbund: Verbund, auftrag: Auftrag, modell: Modell) -> bool:
    """Darf die Anwendung dorthin, wo das Modell liegt (Zone, extern nur auf Wunsch der App)? Ob der Rechner gerade
    antwortet, spielt hier keine Rolle; ein Zonenfehler ist endgültig, ein schlafender Rechner nicht."""
    dienst = verbund.dienste[modell.dienst]
    if dienst.extern:
        return verbund.extern_erlaubt(auftrag, modell)
    knoten = verbund.knoten.get(dienst.knoten) if dienst.knoten else None
    return knoten is not None and knoten.zone in verbund.anwendungen[auftrag.anwendung].zonen


def zone_erlaubt(verbund: Verbund, auftrag: Auftrag, modell: Modell) -> bool:
    """Die Zone passt, und der Rechner des Modells antwortet (externe Anbieter haben keinen)."""
    if not zone_passt(verbund, auftrag, modell):
        return False
    dienst = verbund.dienste[modell.dienst]
    return dienst.extern or verbund.knoten[dienst.knoten or ""].erreichbar


def wirksame_prioritaet(verbund: Verbund, a: Auftrag) -> int:
    """Hintergrund rückt nach der eingestellten Wartezeit auf Normal, damit nichts verhungert."""
    if a.prioritaet == Prioritaet.HINTERGRUND and verbund.zeit_s - a.eingang_s >= verbund.regelwerk.hintergrund_spaetestens_s:
        return int(Prioritaet.NORMAL)
    return int(a.prioritaet)


def rolle(verbund: Verbund, a: Auftrag, knoten: str | None) -> int:
    """0, wenn der Rechner für die Fähigkeit des Auftrags bevorzugt ist (Rolle des Rechners, LS-16), sonst 1."""
    k = verbund.knoten.get(knoten) if knoten else None
    return 0 if k is not None and a.faehigkeit in k.bevorzugt_fuer else 1


def wunsch(a: Auftrag, knoten: str | None) -> int:
    """Rang des Rechners im Wunsch der App (LS-28): 0 für den ersten Wunsch, ohne Wunsch oder nicht genannt hinter allen
    genannten. Ein Wunsch ordnet nur unter Rechnern, die der Auftrag ohnehin nutzen darf; Regeln der Leitstelle gehen vor."""
    return a.rechner_wunsch.index(knoten) if knoten in a.rechner_wunsch else len(a.rechner_wunsch)


def rechner_der_wahl(verbund: Verbund, a: Auftrag) -> set[str]:
    """Die Rechner, auf denen der Auftrag ein Modell aus der Wahl der Anwendung nutzen dürfte (dieselbe Prüfung wie bei der
    Zuteilung: Dienst bereit, Zone, Akku, Vorrang; ohne externe Anbieter). Arbeit nur bei Ruhe wartet auf einen dieser
    Rechner, nicht auf einen, auf dem sie ohnehin nicht rechnen könnte."""
    return {verbund.dienste[m.dienst].knoten for fam in verbund.modellwahl(a) for m in kandidaten(verbund, a, fam, False)
            if verbund.dienste[m.dienst].knoten is not None}


def vorrang_gesperrt(verbund: Verbund, a: Auftrag, m: Modell) -> str | None:
    """Warum der Auftrag dieses Modell nicht bekommt, weil sein Rechner Arbeit mit Vorrang hat (Regelwerk "Vorrang auf dem
    Rechner"); None: er darf. Arbeit mit Vorrang selbst und gleich oder höher eingestufte Arbeit sind nie gesperrt."""
    r = verbund.regelwerk
    if a.wichtig or not r.vorrang_faehigkeiten or a.faehigkeit in r.vorrang_faehigkeiten:
        return None
    if verbund.rang(a) <= min(r.rangfolge.get(f, 10) for f in r.vorrang_faehigkeiten):
        return None
    knoten = verbund.dienste[m.dienst].knoten
    if knoten is None or (was := verbund.vorrang_auf(knoten)) is None:
        return None
    return f"{verbund.knoten[knoten].name} hat Vorrang für {was}"


def hintergrund_gebremst(verbund: Verbund, a: Auftrag, m: Modell) -> str | None:
    """Warum ein Hintergrundauftrag dieses Modell nach der Lage oder der Stufe seines Rechners gerade nicht bekommt; None: er darf.
    Angehalten: kein Hintergrund, auch nicht nach der Fairness-Frist (der Rechner gehört gerade dem Menschen).
    Gedrosselt: wirksam Hintergrund bekommt nur die Grundinstanz, keine weitere. Alles Übrige ist unberührt."""
    if a.prioritaet != Prioritaet.HINTERGRUND:
        return None
    knoten = verbund.dienste[m.dienst].knoten
    k = verbund.knoten.get(knoten) if knoten else None
    if k is None:
        return None
    if k.hintergrund_lage_grund and wirksame_prioritaet(verbund, a) == int(Prioritaet.HINTERGRUND):
        return f"Hintergrund auf {k.name} angehalten: {k.hintergrund_lage_grund}"   # Lage dieses Rechners, mit Fairness-Frist
    if k.hintergrund_stufe == Hintergrundstufe.FREI:
        return None
    if k.hintergrund_stufe == Hintergrundstufe.ANGEHALTEN:
        return f"Hintergrund auf {k.name} angehalten: {k.hintergrund_grund}"
    if m.zusatz and wirksame_prioritaet(verbund, a) == int(Prioritaet.HINTERGRUND):
        return f"Hintergrund auf {k.name} gedrosselt, nur die Grundinstanz: {k.hintergrund_grund}"
    return None


def kandidaten(verbund: Verbund, auftrag: Auftrag, familie: str, mit_extern: bool, gebremst: list[str] | None = None,
               nur_knoten: set[str] | None = None, freigehalten: dict[str, Auftrag] | None = None) -> list[Modell]:
    """Alle Modellinstanzen einer Familie, die der Auftrag nutzen dürfte. Externe nur, wenn ausdrücklich
    gewünscht (festes Modell) oder wenn die Regel Extern ausweichen sie einbezieht. Was die Stufe des Hintergrunds
    verwehrt, fehlt; der Grund kommt nach `gebremst` (dann wartet der Auftrag, statt abgelehnt zu werden)."""
    aus = []
    for m in verbund.modelle.values():
        if m.familie != familie or auftrag.faehigkeit not in m.faehigkeiten:
            continue
        if auftrag.feste_instanz and m.kennung != auftrag.feste_instanz:
            continue                          # Folgeaufruf: nur die Instanz, die das Ergebnis hat
        d = verbund.dienste[m.dienst]
        if auftrag.faehigkeit not in d.faehigkeiten or not d.nutzbar or m.sperre:
            continue
        if d.extern and not mit_extern and not verbund.verlangt(auftrag, familie):
            continue
        if not zone_erlaubt(verbund, auftrag, m):
            continue
        if not verbund.nimmt_arbeit(d.knoten):
            if gebremst is not None:
                k = verbund.knoten[d.knoten]
                gebremst.append(f"{k.name}: Akku {k.akku_prozent} %, unter {verbund.regelwerk.akku_stopp_prozent:.0f} % keine neue Arbeit")
            continue
        if nur_knoten is not None and d.knoten not in nur_knoten:
            continue                          # Arbeit nur bei Ruhe: dieser Rechner ist gerade nicht ruhig
        if freigehalten and d.knoten in freigehalten:
            if gebremst is not None:
                gebremst.append(wichtig_haelt(verbund, freigehalten[d.knoten], d.knoten))
            continue                          # ein wichtiger Auftrag wartet auf diesen Rechner (LS-23)
        if (grund := vorrang_gesperrt(verbund, auftrag, m)) is not None or (grund := hintergrund_gebremst(verbund, auftrag, m)) is not None:
            if gebremst is not None:
                gebremst.append(grund)
            continue
        aus.append(m)
    return aus


def schlafende_fuer(verbund: Verbund, modelle: list[Modell]) -> list[str]:
    """Die Rechner der Modelle, wenn jedes Modell im eigenen Netz auf einem schlafenden Rechner liegt; sonst leer.
    Externe Anbieter zählen nicht mit: wären sie für den Auftrag nutzbar, gäbe es einen Kandidaten."""
    vor_ort = [verbund.dienste[m.dienst].knoten for m in modelle if not verbund.dienste[m.dienst].extern]
    if not vor_ort or not all(k in verbund.knoten and verbund.knoten[k].schlaeft for k in vor_ort):
        return []
    return sorted({k for k in vor_ort if k is not None})


def ablehnungsgrund(verbund: Verbund, auftrag: Auftrag, wahl: list[str]) -> Wartegrund:
    """Warum es für den Auftrag keinen Kandidaten gibt, als Wort und Satz. Reihenfolge: die Zone passt wirklich nicht
    (endgültig), alle passenden Rechner schlafen (die App wartet, bis einer wach ist), sonst ist der Dienst gerade weg."""
    def absage(grund: str, satz: str, schlafend: list[str] | None = None) -> Wartegrund:
        return Wartegrund(auftrag=auftrag.kennung, zustand=Auftragszustand.ABGELEHNT, grund=grund, begruendung=satz,
                          schlafende_knoten=schlafend or [])
    if auftrag.feste_instanz and auftrag.feste_instanz not in verbund.modelle:
        return absage("instanz_weg", "die Instanz, die das Ergebnis hat, läuft nicht mehr; der Aufruf muss von vorn beginnen")
    passende = [m for m in verbund.modelle.values() if m.familie in wahl and auftrag.faehigkeit in m.faehigkeiten]
    if not passende:
        if len(wahl) == 1:
            return absage("kein_modell", f"Modell {wahl[0]} ist im Verbund nicht bekannt oder kann das nicht")
        return absage("kein_modell", f"keines der Modelle {', '.join(wahl)} ist im Verbund bekannt oder kann das")
    in_zone = [m for m in passende if zone_passt(verbund, auftrag, m)]
    if not in_zone:
        return absage("zone_nicht_erlaubt", "das Modell liegt nur in Zonen, die die Anwendung nicht nutzen darf")
    if schlafend := schlafende_fuer(verbund, in_zone):
        return absage("rechner_schlaeft", schlaf_satz([verbund.knoten[k].name for k in schlafend]), schlafend)
    if all(m.sperre for m in in_zone):
        m = in_zone[0]
        return absage("dienst_gesperrt", f"{m.name} ist gesperrt ({m.sperre}); er läuft erst wieder, wenn die Sperre im Maschinenraum "
                                         "von Hand aufgehoben ist")
    return absage("dienst_nicht_erreichbar", "der Dienst mit diesem Modell ist gerade nicht erreichbar")


def platz_frei(verbund: Verbund, m: Modell, bedarf: Bedarf) -> bool:
    """Ein Platz auf dem Modell und, wo der Dienst Grenzen je Minute hat, Raum im Fenster für den Bedarf (Anfrage und Token
    des Auftrags samt dem, was in diesem Zuteillauf schon vergeben ist)."""
    return len(verbund.belegung(m.kennung)) < verbund.plaetze(m) and verbund.anfrage_frei_in_s(m.dienst, bedarf) == 0


def _mit_vergebenem(vergeben: dict[str, Bedarf], dienst: str, a: Auftrag) -> Bedarf:
    """Bedarf des Auftrags samt dem, was dieser Zuteillauf auf dem Dienst schon vergeben hat."""
    return vergeben.get(dienst, Bedarf()) + a.bedarf


def reihenfolge(verbund: Verbund) -> list[Auftrag]:
    """Wichtige Aufträge zuerst, untereinander nach Eingang (LS-23: der Nutzer hat sie markiert, sie gehen allem vor). Dann
    Einzelarbeit vor Masse und Arbeit nur bei Ruhe (LS-24; Nutzer 31.10.2026: "nicht so privilegiert, die können auch
    laufen, wenn nichts los ist"); innerhalb davon nach dem Rang der Fähigkeit (Regelwerk "Rangfolge", Sprachausgabe
    zuerst, Einbettung zuletzt), innerhalb eines Rangs nach Priorität der Anwendung, dann nach Eingang."""
    def schluessel(a: Auftrag) -> tuple:
        if a.wichtig:
            return (0, 0, 0, 0, a.eingang_s)
        return (1, int(verbund.nur_bei_ruhe(a)), verbund.rang(a), -wirksame_prioritaet(verbund, a), a.eingang_s)
    return sorted(verbund.wartende_auftraege(), key=schluessel)


def wichtig_haelt(verbund: Verbund, w: Auftrag, knoten: str) -> str:
    """Grund für andere Arbeit, solange ein wichtiger Auftrag auf diesen Rechner wartet (LS-23, Auskunft an die App)."""
    app = verbund.anwendungen.get(w.anwendung)
    name = verbund.knoten[knoten].name if knoten in verbund.knoten else knoten
    seit = max(0, round(verbund.zeit_s - w.eingang_s))
    etwa = f", etwa {w.voraussichtlich_s:.0f} s" if w.voraussichtlich_s else ""
    return f"{name} ist für einen wichtigen Auftrag von {app.name if app else w.anwendung} freigehalten (wartet seit {seit} s{etwa})"


def platz(verbund: Verbund, a: Auftrag) -> tuple[int, int] | None:
    """Platz eines wartenden Auftrags unter den wartenden seiner Fähigkeit, in der Reihenfolge des Zuteilers, und wie
    viele es sind; Aufträge anderer Apps zählen mit (HELF-130: "Platz 2" beim Bilddienst). None, wenn er nicht wartet."""
    gleiche = [x.kennung for x in reihenfolge(verbund) if x.faehigkeit == a.faehigkeit]
    return (gleiche.index(a.kennung) + 1, len(gleiche)) if a.kennung in gleiche else None


def _wunsch_satz(verbund: Verbund, a: Auftrag, knoten: str | None) -> str:
    """Zur Begründung: wie der Rechner zum Wunsch der App steht (LS-28); ohne Wunsch nichts."""
    if not a.rechner_wunsch:
        return ""
    if knoten == a.rechner_wunsch[0]:
        return ", wie von der App gewünscht"
    erster = verbund.knoten.get(a.rechner_wunsch[0])
    return f", statt des gewünschten {erster.name if erster else a.rechner_wunsch[0]}"


def _auf_wunschrechner_laden(verbund: Verbund, a: Auftrag, familie: str, mit_extern: bool, nur_knoten: set[str] | None,
                             freigehalten: dict[str, Auftrag], rang_geladen: int, geplanter_speicher: dict[str, float],
                             messwerk: Messwerk) -> Zuteilung | None:
    """Eine Zuteilung zum Laden auf einem Rechner, den die App lieber hat als den, auf dem das Modell schon geladen ist
    (LS-28), wenn es dort ohne Entladen passt; sonst None (dann rechnet es, wo es liegt)."""
    if rang_geladen == 0 or not a.rechner_wunsch:
        return None
    besser = []
    for m in kandidaten(verbund, a, familie, mit_extern, None, nur_knoten, freigehalten):
        d = verbund.dienste[m.dienst]
        if d.extern or m.zustand != Modellzustand.FREI or wunsch(a, d.knoten) >= rang_geladen or not m.ladbar(verbund.zeit_s):
            continue
        plan = planen(verbund, d.knoten, m.gb + geplanter_speicher.get(d.knoten, 0.0), messwerk, familie=m.familie, fuer_arbeit=a.arbeit,
                      anforderung=True)
        if plan.passt and not plan.entladen:
            besser.append((wunsch(a, d.knoten), plan.aufwand_s, plan, m, d))
    if not besser:
        return None
    _, _, p, m, d = min(besser, key=lambda t: (t[0], t[1]))
    return Zuteilung(auftrag=a.kennung, dienst=d.kennung, knoten=d.knoten, modell=m.kennung, laden=True, direkt=False,
                     begruendung=f"{m.name} wird auf {d.name} {'gestartet' if d.maschinenraum else 'geladen'}, wie von der App gewünscht "
                                 f"({komma(p.frei_gb)} GB frei, etwa {p.aufwand_s:.0f} s)")


def zuteilen(verbund: Verbund, messwerk: Messwerk, mit_extern: bool = False) -> Zuteilergebnis:
    """Teilt alle wartenden Aufträge zu, soweit möglich. Verändert den Verbund nicht."""
    ergebnis = Zuteilergebnis()
    if verbund.betriebsmodus != Betriebsmodus.NORMAL:
        for a in verbund.wartende_auftraege():
            ergebnis.wartend.append(Wartegrund(auftrag=a.kennung, zustand=a.zustand, begruendung=f"Hauptregler steht auf {verbund.betriebsmodus.value}, nichts Neues wird gestartet"))
        return ergebnis
    vergeben_plaetze: dict[str, int] = {}       # Modellkennung -> in diesem Lauf schon vergebene Plätze
    vergeben_bedarf: dict[str, Bedarf] = {}     # Dienstkennung -> in diesem Lauf schon vergebene Anfragen und Token (Grenzen je Minute)
    geplanter_speicher: dict[str, float] = {}   # Knoten -> in diesem Lauf schon verplante GB
    je_anwendung: dict[str, int] = {}
    for a in verbund.offene_auftraege():
        if a.zustand in (Auftragszustand.LAEUFT, Auftragszustand.ZUGETEILT):
            je_anwendung[a.anwendung] = je_anwendung.get(a.anwendung, 0) + 1
    ruhige = {k for k in verbund.knoten if verbund.ruhe_auf(k).frei and verbund.nimmt_arbeit(k)}   # gesperrter Akku ist keine Ruhe
    freigehalten: dict[str, Auftrag] = {}       # Rechner -> wichtiger Auftrag, der dort wartet (LS-23): dort startet nichts anderes

    for a in reihenfolge(verbund):
        app = verbund.anwendungen[a.anwendung]
        if a.faehigkeit not in app.faehigkeiten:
            ergebnis.abgelehnt.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.ABGELEHNT, grund="faehigkeit_nicht_erlaubt", begruendung="Fähigkeit für diese Anwendung nicht erlaubt"))
            continue
        if (gehalten := verbund.pruefung_haelt(a)) is not None:
            ergebnis.wartend.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.EINGEREIHT, begruendung=gehalten))
            continue
        wahl = verbund.modellwahl(a)
        if not wahl:
            ergebnis.abgelehnt.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.ABGELEHNT, grund="modell_fehlt", begruendung=MODELL_FEHLT))
            continue
        nur_knoten: set[str] | None = None
        if verbund.nur_bei_ruhe(a):
            orte = rechner_der_wahl(verbund, a)
            if orte and not orte & ruhige:
                naechste = min((verbund.ruhe_auf(k) for k in orte), key=lambda r: r.in_s if r.in_s is not None else float("inf"))
                ergebnis.wartend.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.WARTET_RUHE, begruendung=naechste.grund, voraussichtlich_s=naechste.in_s))
                continue
            # Ohne nutzbaren Rechner gerade (Akku, Hintergrundstufe, Vorrang): keine Einschränkung, dann nennt die Prüfung der
            # Kandidaten den Grund und der Auftrag wartet damit, statt abgelehnt zu werden
            nur_knoten = ruhige if orte else None
        if a.prioritaet == Prioritaet.HINTERGRUND and not verbund.hintergrund_erlaubt:
            ergebnis.wartend.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.EINGEREIHT, begruendung="Hintergrund ist am Hauptregler angehalten"))
            continue
        if je_anwendung.get(a.anwendung, 0) >= app.gleichzeitig:
            ergebnis.wartend.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.EINGEREIHT, begruendung=f"Kontingent erreicht: {app.gleichzeitig} gleichzeitig"))
            continue

        gefunden: Zuteilung | None = None
        warte: Wartegrund | None = None
        gebremst: list[str] = []
        # 1. Die Reihenfolge der Anwendung gilt streng: das erste ihrer Modelle, das geht (einen Kandidaten hat), dort geladen
        # mit freiem Platz; eine Alternative nur, wenn das verlangte Modell nicht geht, nie, weil sie schon geladen ist (das
        # Ausweichen eines wartenden Auftrags auf eine geladene Alternative ist die Regel "Ausweichen")
        erstes = next((fam for fam in wahl if kandidaten(verbund, a, fam, mit_extern, nur_knoten=nur_knoten, freigehalten=freigehalten)), wahl[0])
        geladene: list[tuple[tuple[int, int, float], Modell]] = []
        for m in kandidaten(verbund, a, erstes, mit_extern, gebremst, nur_knoten, freigehalten):
            if (m.zustand in (Modellzustand.GELADEN, Modellzustand.RECHNET) and platz_frei(verbund, m, _mit_vergebenem(vergeben_bedarf, m.dienst, a))
                    and vergeben_plaetze.get(m.kennung, 0) < verbund.plaetze(m) - len(verbund.belegung(m.kennung))):
                d = verbund.dienste[m.dienst]
                bevorzugt = 0 if (a.prioritaet == Prioritaet.HINTERGRUND and verbund.hintergrund_knoten_bevorzugt and d.knoten == verbund.hintergrund_knoten_bevorzugt) else 1
                belegt = (len(verbund.belegung(m.kennung)) + vergeben_plaetze.get(m.kennung, 0)) / max(1, verbund.plaetze(m))
                geladene.append(((bevorzugt, wunsch(a, d.knoten), rolle(verbund, a, d.knoten), belegt), m))
        if geladene:
            _, m = sorted(geladene, key=lambda t: t[0])[0]
            d = verbund.dienste[m.dienst]
            # Wunsch der App (LS-28): liegt das Modell nur auf einem weniger gewünschten Rechner, lädt es der gewünschte,
            # wenn es dort ohne Entladen passt; sonst rechnet es, wo es schon liegt
            if (wunschladen := _auf_wunschrechner_laden(verbund, a, erstes, mit_extern, nur_knoten, freigehalten, wunsch(a, d.knoten),
                                                        geplanter_speicher, messwerk)) is not None:
                gefunden = wunschladen
                geplanter_speicher[gefunden.knoten] = geplanter_speicher.get(gefunden.knoten, 0.0) + verbund.modelle[gefunden.modell].gb
            else:
                gefunden = Zuteilung(auftrag=a.kennung, dienst=d.kennung, knoten=d.knoten, modell=m.kennung, laden=False, direkt=a.prioritaet >= Prioritaet.HOCH,
                                     begruendung=f"{m.name} ist auf {d.name} geladen und frei" + (" (Direktweg)" if a.prioritaet >= Prioritaet.HOCH else "")
                                     + _wunsch_satz(verbund, a, d.knoten))
        if gefunden is None:
            # 2. Das erste Modell der Wahl, das geht: geladen, aber belegt -> warten auf Platz; sonst laden, wenn es passt
            for fam in wahl:
                ks = kandidaten(verbund, a, fam, mit_extern, gebremst, nur_knoten, freigehalten)
                if not ks:
                    continue
                belegt = [m for m in ks if m.zustand in (Modellzustand.GELADEN, Modellzustand.RECHNET, Modellzustand.LAEDT)]
                if belegt:
                    m = belegt[0]
                    if (frei := verbund.frei(m.dienst, _mit_vergebenem(vergeben_bedarf, m.dienst, a))).in_s > 0:
                        d = verbund.dienste[m.dienst]
                        warte = Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.EINGEREIHT, wartet_auf_familie=fam, wartet_auf_knoten=d.knoten,
                                           voraussichtlich_s=frei.in_s, begruendung=f"{d.name}: {frei.grund}, wieder frei in etwa {frei.in_s:.0f} s")
                        break
                    rest = max((messwerk.rest_s(x.anwendung, x.faehigkeit.value, x.fortschritt_s) for x in verbund.belegung(m.kennung)), default=None)
                    d = verbund.dienste[m.dienst]
                    warte = Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.EINGEREIHT, wartet_auf_familie=fam, wartet_auf_knoten=d.knoten, voraussichtlich_s=rest,
                                       begruendung=f"{m.name} auf {d.name} ist belegt" + (f", frei in etwa {rest:.0f} s" if rest is not None else ""))
                    break
                # nicht geladen: passt es irgendwo ohne Entladen?
                plaene = []
                gesperrt: list[Modell] = []
                for m in ks:
                    d = verbund.dienste[m.dienst]
                    if d.extern:
                        gefunden = Zuteilung(auftrag=a.kennung, dienst=d.kennung, knoten=None, modell=m.kennung, laden=False, direkt=False, begruendung=f"extern bei {d.name}")
                        break
                    if not m.ladbar(verbund.zeit_s):
                        gesperrt.append(m)
                        continue
                    plan = planen(verbund, d.knoten, m.gb + geplanter_speicher.get(d.knoten, 0.0), messwerk, familie=m.familie, fuer_arbeit=a.arbeit,
                                  anforderung=True)
                    plaene.append((plan, m, d))
                if gefunden:
                    break
                if not plaene and gesperrt:
                    m = min(gesperrt, key=lambda x: x.ladesperre_bis_s or 0.0)
                    d = verbund.dienste[m.dienst]
                    rest = max(1.0, (m.ladesperre_bis_s or verbund.zeit_s) - verbund.zeit_s)
                    warte = Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.WARTET_SPEICHER, wartet_auf_familie=fam, wartet_auf_knoten=d.knoten, voraussichtlich_s=rest,
                                       begruendung=f"{d.name} hat das Laden von {m.name} abgelehnt ({m.ladesperre_grund}); neuer Versuch in etwa {rest:.0f} s")
                    break
                passende = [(p, m, d) for p, m, d in plaene if p.passt and not p.entladen]
                if passende:
                    bevorzugt = verbund.hintergrund_knoten_bevorzugt if a.prioritaet == Prioritaet.HINTERGRUND else None
                    p, m, d = sorted(passende, key=lambda t: (0 if t[2].knoten == bevorzugt else 1, wunsch(a, t[2].knoten), rolle(verbund, a, t[2].knoten),
                                                              t[0].aufwand_s))[0]
                    gefunden = Zuteilung(auftrag=a.kennung, dienst=d.kennung, knoten=d.knoten, modell=m.kennung, laden=True, direkt=False,
                                         begruendung=f"{m.name} wird auf {d.name} {'gestartet' if d.maschinenraum else 'geladen'} ({komma(p.frei_gb)} GB frei, etwa {p.aufwand_s:.0f} s)"
                                         + _wunsch_satz(verbund, a, d.knoten))
                    geplanter_speicher[d.knoten] = geplanter_speicher.get(d.knoten, 0.0) + m.gb
                    break
                if plaene:
                    # Warten dort, wo Speicher am ehesten frei wird (passender Plan zuerst, dann kürzeste Frist)
                    p, m, d = sorted(plaene, key=lambda t: (0 if t[0].passt else 1, t[0].frei_nach_s if t[0].frei_nach_s is not None else float("inf")))[0]
                    warte = Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.WARTET_SPEICHER, wartet_auf_familie=fam, wartet_auf_knoten=d.knoten, voraussichtlich_s=p.frei_nach_s,
                                       begruendung=p.begruendung)
                    break
        if gefunden:
            ergebnis.zuteilungen.append(gefunden)
            vergeben_plaetze[gefunden.modell] = vergeben_plaetze.get(gefunden.modell, 0) + 1
            vergeben_bedarf[gefunden.dienst] = vergeben_bedarf.get(gefunden.dienst, Bedarf()) + a.bedarf
            je_anwendung[a.anwendung] = je_anwendung.get(a.anwendung, 0) + 1
        elif warte:
            ergebnis.wartend.append(warte)
            if a.wichtig and warte.wartet_auf_knoten and warte.wartet_auf_knoten not in freigehalten:
                freigehalten[warte.wartet_auf_knoten] = a
        elif gebremst:
            ergebnis.wartend.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.EINGEREIHT, begruendung=gebremst[0]))
        else:
            ergebnis.abgelehnt.append(ablehnungsgrund(verbund, a, wahl))
    return ergebnis
