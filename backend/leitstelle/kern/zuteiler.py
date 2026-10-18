"""Zuteiler: welcher Dienst, welches Modell, welcher Knoten für einen wartenden Auftrag.

Reihenfolge der Prüfung (ARCHITEKTUR 5.1): Rechte der Anwendung, Kette, Speicher, Plätze,
Priorität mit Fairness, Direktweg. Jede Entscheidung trägt eine Begründung in Worten.
Der Zuteiler lädt nicht selbst; er sagt, was zu laden wäre (Zuteilung mit laden=True), das
Ausführen übernimmt der Vollzug (Dienst-Adapter, im Test der Schein-Verbund).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .messungen import Messwerk
from .modelle import Auftrag, Modell, Verbund
from .speicherplaner import planen
from .werte import Auftragszustand, Betriebsmodus, Faehigkeit, Modellzustand, Prioritaet, Zone
from .text import komma


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
    voraussichtlich_s: float | None = None


class Zuteilergebnis(BaseModel):
    zuteilungen: list[Zuteilung] = Field(default_factory=list)
    wartend: list[Wartegrund] = Field(default_factory=list)
    abgelehnt: list[Wartegrund] = Field(default_factory=list)


def zone_erlaubt(verbund: Verbund, auftrag: Auftrag, modell: Modell) -> bool:
    dienst = verbund.dienste[modell.dienst]
    app = verbund.anwendungen[auftrag.anwendung]
    if dienst.extern:
        return verbund.extern_erlaubt(auftrag, modell)
    knoten = verbund.knoten[dienst.knoten] if dienst.knoten else None
    return knoten is not None and knoten.erreichbar and knoten.zone in app.zonen


def kandidaten(verbund: Verbund, auftrag: Auftrag, familie: str, mit_extern: bool) -> list[Modell]:
    """Alle Modellinstanzen einer Familie, die der Auftrag nutzen dürfte. Externe nur, wenn ausdrücklich
    gewünscht (festes Modell) oder wenn die Regel Extern ausweichen sie einbezieht."""
    aus = []
    for m in verbund.modelle.values():
        if m.familie != familie or auftrag.faehigkeit not in m.faehigkeiten:
            continue
        if auftrag.feste_instanz and m.kennung != auftrag.feste_instanz:
            continue                          # Folgeaufruf: nur die Instanz, die das Ergebnis hat
        d = verbund.dienste[m.dienst]
        if auftrag.faehigkeit not in d.faehigkeiten or not d.nutzbar:
            continue
        if d.extern and not mit_extern and auftrag.festes_modell != familie:
            continue
        if not zone_erlaubt(verbund, auftrag, m):
            continue
        aus.append(m)
    return aus


def ablehnungsgrund(verbund: Verbund, auftrag: Auftrag, kette: list[str]) -> tuple[str, str]:
    """Warum es für den Auftrag keinen Kandidaten gibt, als Wort und Satz."""
    if auftrag.feste_instanz and auftrag.feste_instanz not in verbund.modelle:
        return "instanz_weg", "die Instanz, die das Ergebnis hat, läuft nicht mehr; der Aufruf muss von vorn beginnen"
    passende = [m for m in verbund.modelle.values() if m.familie in kette and auftrag.faehigkeit in m.faehigkeiten]
    if not passende:
        if auftrag.festes_modell:
            return "kein_modell", f"Modell {auftrag.festes_modell} ist im Verbund nicht bekannt oder kann das nicht"
        return "kein_modell", "kein Modell der Kette kann diese Fähigkeit"
    if not any(zone_erlaubt(verbund, auftrag, m) for m in passende):
        return "zone_nicht_erlaubt", "das Modell liegt nur in Zonen, die die Anwendung nicht nutzen darf"
    return "dienst_nicht_erreichbar", "der Dienst mit diesem Modell ist gerade nicht erreichbar"


def platz_frei(verbund: Verbund, m: Modell, schon_vergeben: int = 0) -> bool:
    """Ein Platz auf dem Modell und, wo der Dienst eine Grenze je Minute hat, eine Anfrage im Fenster."""
    return len(verbund.belegung(m.kennung)) < verbund.plaetze(m) and verbund.anfrage_frei_in_s(m.dienst, schon_vergeben) == 0


def wirksame_prioritaet(verbund: Verbund, a: Auftrag) -> int:
    """Hintergrund rückt nach der eingestellten Wartezeit auf Normal, damit nichts verhungert."""
    if a.prioritaet == Prioritaet.HINTERGRUND and verbund.zeit_s - a.eingang_s >= verbund.regelwerk.hintergrund_spaetestens_s:
        return int(Prioritaet.NORMAL)
    return int(a.prioritaet)


def reihenfolge(verbund: Verbund) -> list[Auftrag]:
    """Einbettung zuerst (Nutzer 18.10.2026: "höchste Priorität"; kurz, und Suchen warten sonst hinter langen Texten),
    dann nach Priorität, dann nach Eingang."""
    return sorted(verbund.wartende_auftraege(),
                  key=lambda a: (a.faehigkeit != Faehigkeit.EINBETTUNG, -wirksame_prioritaet(verbund, a), a.eingang_s))


def zuteilen(verbund: Verbund, messwerk: Messwerk, mit_extern: bool = False) -> Zuteilergebnis:
    """Teilt alle wartenden Aufträge zu, soweit möglich. Verändert den Verbund nicht."""
    ergebnis = Zuteilergebnis()
    if verbund.betriebsmodus != Betriebsmodus.NORMAL:
        for a in verbund.wartende_auftraege():
            ergebnis.wartend.append(Wartegrund(auftrag=a.kennung, zustand=a.zustand, begruendung=f"Hauptregler steht auf {verbund.betriebsmodus.value}, nichts Neues wird gestartet"))
        return ergebnis
    vergeben_plaetze: dict[str, int] = {}       # Modellkennung -> in diesem Lauf schon vergebene Plätze
    vergeben_anfragen: dict[str, int] = {}      # Dienstkennung -> in diesem Lauf schon vergebene Anfragen (Grenze je Minute)
    geplanter_speicher: dict[str, float] = {}   # Knoten -> in diesem Lauf schon verplante GB
    je_anwendung: dict[str, int] = {}
    for a in verbund.offene_auftraege():
        if a.zustand in (Auftragszustand.LAEUFT, Auftragszustand.ZUGETEILT):
            je_anwendung[a.anwendung] = je_anwendung.get(a.anwendung, 0) + 1

    for a in reihenfolge(verbund):
        app = verbund.anwendungen[a.anwendung]
        if a.faehigkeit not in app.faehigkeiten:
            ergebnis.abgelehnt.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.ABGELEHNT, grund="faehigkeit_nicht_erlaubt", begruendung="Fähigkeit für diese Anwendung nicht erlaubt"))
            continue
        if a.prioritaet == Prioritaet.HINTERGRUND and not verbund.hintergrund_erlaubt:
            ergebnis.wartend.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.EINGEREIHT, begruendung="Hintergrund ist am Hauptregler angehalten"))
            continue
        if a.prioritaet == Prioritaet.HINTERGRUND and not verbund.hintergrund_an and wirksame_prioritaet(verbund, a) == int(Prioritaet.HINTERGRUND):
            ergebnis.wartend.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.EINGEREIHT, begruendung="Hintergrund ist angehalten"))
            continue
        if je_anwendung.get(a.anwendung, 0) >= app.gleichzeitig:
            ergebnis.wartend.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.EINGEREIHT, begruendung=f"Kontingent erreicht: {app.gleichzeitig} gleichzeitig"))
            continue
        kette = verbund.kette(a)
        if not kette:
            ergebnis.abgelehnt.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.ABGELEHNT, grund="kein_modell", begruendung="kein Modell angegeben und keine Kette für diese Fähigkeit eingerichtet"))
            continue

        gefunden: Zuteilung | None = None
        warte: Wartegrund | None = None
        # 1. Geladene zuerst (über die ganze Kette), mit freiem Platz
        suche = kette if verbund.regelwerk.geladene_zuerst else kette[:1]
        geladene: list[tuple[int, Modell]] = []
        for i, fam in enumerate(suche):
            for m in kandidaten(verbund, a, fam, mit_extern):
                if (m.zustand in (Modellzustand.GELADEN, Modellzustand.RECHNET) and platz_frei(verbund, m, vergeben_anfragen.get(m.dienst, 0))
                        and vergeben_plaetze.get(m.kennung, 0) < verbund.plaetze(m) - len(verbund.belegung(m.kennung))):
                    d = verbund.dienste[m.dienst]
                    bevorzugt = 0 if (a.prioritaet == Prioritaet.HINTERGRUND and verbund.hintergrund_knoten_bevorzugt and d.knoten == verbund.hintergrund_knoten_bevorzugt) else 1
                    geladene.append((bevorzugt * 100 + i, m))
        if geladene:
            i, m = sorted(geladene, key=lambda t: t[0])[0]
            d = verbund.dienste[m.dienst]
            gefunden = Zuteilung(auftrag=a.kennung, dienst=d.kennung, knoten=d.knoten, modell=m.kennung, laden=False, direkt=a.prioritaet >= Prioritaet.HOCH,
                                 begruendung=f"{m.name} ist auf {d.name} geladen und frei" + (" (Direktweg)" if a.prioritaet >= Prioritaet.HOCH else ""))
        if gefunden is None:
            # 2. Erste Familie der Kette: geladen, aber belegt -> warten auf Platz; sonst laden, wenn es passt
            for fam in kette:
                ks = kandidaten(verbund, a, fam, mit_extern)
                if not ks:
                    continue
                belegt = [m for m in ks if m.zustand in (Modellzustand.GELADEN, Modellzustand.RECHNET, Modellzustand.LAEDT)]
                if belegt:
                    m = belegt[0]
                    if (frei_in := verbund.anfrage_frei_in_s(m.dienst, vergeben_anfragen.get(m.dienst, 0))) > 0:
                        d = verbund.dienste[m.dienst]
                        gesperrt = (d.gesperrt_bis_s or 0.0) > verbund.zeit_s
                        grenze = "Dienst meldete Überlast" if gesperrt else f"Grenze von {d.anfragen_je_minute} Anfragen je Minute erreicht"
                        warte = Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.EINGEREIHT, wartet_auf_familie=fam, wartet_auf_knoten=d.knoten,
                                           voraussichtlich_s=frei_in, begruendung=f"{d.name}: {grenze}, wieder frei in etwa {frei_in:.0f} s")
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
                    plan = planen(verbund, d.knoten, m.gb + geplanter_speicher.get(d.knoten, 0.0), messwerk, familie=m.familie, fuer_arbeit=a.arbeit)
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
                    p, m, d = sorted(passende, key=lambda t: (0 if t[2].knoten == bevorzugt else 1, t[0].aufwand_s))[0]
                    gefunden = Zuteilung(auftrag=a.kennung, dienst=d.kennung, knoten=d.knoten, modell=m.kennung, laden=True, direkt=False,
                                         begruendung=f"{m.name} wird auf {d.name} geladen ({komma(p.frei_gb)} GB frei, etwa {p.aufwand_s:.0f} s)")
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
            vergeben_anfragen[gefunden.dienst] = vergeben_anfragen.get(gefunden.dienst, 0) + 1
            je_anwendung[a.anwendung] = je_anwendung.get(a.anwendung, 0) + 1
        elif warte:
            ergebnis.wartend.append(warte)
        else:
            grund, satz = ablehnungsgrund(verbund, a, kette)
            ergebnis.abgelehnt.append(Wartegrund(auftrag=a.kennung, zustand=Auftragszustand.ABGELEHNT, grund=grund, begruendung=satz))
    return ergebnis
