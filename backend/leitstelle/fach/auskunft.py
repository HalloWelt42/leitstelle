"""Auskunft für Apps (Arbeitslogik 07.11.2026, LS-18, PROTOKOLL 6.5): was jede App über das Haus lesen darf, damit sie
selbst entscheiden kann (welches Modell, wann, wie dringend). Auslastung je App, Modelle je Rechner, geschätzte Dauer,
Rangfolge und Priorität; nie Titel, Texte oder Eingaben eines Auftrags."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import version
from ..kern.werte import Auftragszustand, Faehigkeit, Modellzustand
from ..kern.modelle import Auftrag
from ..kern.zuteiler import reihenfolge, zuteilen
from ..protokoll.fassade import (AppAuskunft, AuftragAuskunft, Einschaetzung, Einschaetzungsanfrage, Lageauskunft, ModellAuskunft,
                                 PruefungAuskunft, RechnerAuskunft, WichtigerAuftrag)

if TYPE_CHECKING:
    from .betrieb import Betrieb

#: Zustände, in denen ein Auftrag rechnet (Restdauer statt Wartezeit)
RECHNET = (Auftragszustand.LAEUFT, Auftragszustand.ZUGETEILT)


def lageauskunft(b: Betrieb, fragt: str | None) -> Lageauskunft:
    """Die Auskunft für die App `fragt` (Kennung; None: ohne Schlüssel aus dem Heimnetz). Eigene Aufträge sind markiert."""
    v = b.verbund
    jetzt = v.zeit_s
    apps: dict[str, AppAuskunft] = {}
    for a in sorted(v.offene_auftraege(), key=lambda x: x.eingang_s):
        app = v.anwendungen.get(a.anwendung)
        eintrag = apps.setdefault(a.anwendung, AppAuskunft(name=app.name if app else a.anwendung, eigene=a.anwendung == fragt,
                                                              laufend=0, wartend=0, auftraege=[]))
        m = v.modelle.get(a.modell or "")
        rechnet = a.zustand in RECHNET
        if rechnet:
            eintrag.laufend += 1
            rest = b.messwerk.rest_s(a.anwendung, a.faehigkeit.value, a.fortschritt_s)
        else:
            eintrag.wartend += 1
            rest = a.voraussichtlich_s
        rechner = v.knoten[a.knoten].name if a.knoten in v.knoten else None
        eintrag.auftraege.append(AuftragAuskunft(
            kennung=a.kennung, eigener=a.anwendung == fragt, faehigkeit=a.faehigkeit, rang=v.rang(a), prioritaet=a.prioritaet,
            zustand=a.zustand, modell=m.familie if m else (a.festes_modell or a.wartet_auf_familie), modell_name=m.name if m else None,
            rechner=rechner, seit_s=round(jetzt - a.eingang_s, 1), rest_s=round(rest, 1) if rest is not None else None,
            art=a.art, wichtig=a.wichtig, grund=(a.begruendung or None) if a.anwendung == fragt and not rechnet else None))
    r = v.regelwerk
    rechner_liste = []
    for k in sorted(v.knoten.values(), key=lambda x: x.name):
        av = b.agenten.verbindung(k.kennung)
        modelle = [ModellAuskunft(familie=m.familie, name=m.name, zustand=m.zustand.value, auftraege=len(v.belegung(m.kennung)))
                   for m in sorted(v.modelle_auf(k.kennung), key=lambda x: x.name) if m.zustand != Modellzustand.FREI]
        rechner_liste.append(RechnerAuskunft(
            name=k.name, erreichbar=k.erreichbar, schlaeft=k.schlaeft,
            cpu_prozent=av.messwerte.cpu_prozent if av and av.messwerte else None,
            frei_gb=round(v.frei_gb(k.kennung), 2), budget_gb=round(k.budget_gb(r.budget_reserve_gb), 2),
            akku_prozent=k.akku_prozent, akku_gesperrt=k.akku_gesperrt, akku_probe=v.akku_probewert(k.kennung) is not None,
            vorrang=v.vorrang_auf(k.kennung),
            bevorzugt_fuer=[f for f in Faehigkeit if f in k.bevorzugt_fuer], modelle=modelle))
    f = v.prueffenster if v.pruefung_offen else None
    pruefung = None
    if f is not None:
        app = v.anwendungen.get(f.anwendung)
        pruefung = PruefungAuskunft(anwendung=app.name if app else f.anwendung, bis_s=f.bis_s, durchlass=list(r.pruefung_durchlass))
    return Lageauskunft(fassung=version(), zeit_s=jetzt, hauptregler=v.betriebsmodus.value, lage=b.kern.lage.value,
                        rangfolge=dict(r.rangfolge), apps=list(apps.values()), rechner=rechner_liste, pruefung=pruefung)


PROBE = "einschaetzung"


def einschaetzung(b: Betrieb, fragt: str, anfrage: Einschaetzungsanfrage, faehigkeit: Faehigkeit, familie: str | None,
                  alternativen: list[str]) -> Einschaetzung:
    """Spielt den Auftrag auf einer Kopie des Verbunds durch, mit demselben Zuteiler wie im Betrieb (eine Wahrheit):
    bekäme er jetzt einen Platz, oder worauf wartet er, wie lange etwa und wer kommt vorher dran."""
    v = b.verbund.model_copy(deep=True)
    a = Auftrag(kennung=PROBE, anwendung=fragt, faehigkeit=faehigkeit, prioritaet=v.anwendungen[fragt].prioritaet, eingang_s=v.zeit_s,
                festes_modell=familie, alternativen=alternativen, art=anfrage.art, wichtig=anfrage.wichtig, laufzeit_s=0.0)
    v.auftraege[a.kennung] = a
    vor_dir = next((i for i, x in enumerate(reihenfolge(v)) if x.kennung == PROBE), 0)
    erg = zuteilen(v, b.messwerk)
    wichtige = [WichtigerAuftrag(anwendung=v.anwendungen[x.anwendung].name if x.anwendung in v.anwendungen else x.anwendung,
                                 faehigkeit=x.faehigkeit, rechner=v.knoten[x.knoten].name if x.knoten in v.knoten else None, zustand=x.zustand,
                                 seit_s=round(v.zeit_s - x.eingang_s, 1))
                for x in v.offene_auftraege() if x.wichtig and x.kennung != PROBE]
    name = lambda kn: v.knoten[kn].name if kn in v.knoten else None   # noqa: E731
    if z := next((x for x in erg.zuteilungen if x.auftrag == PROBE), None):
        laden = b.messwerk.ladezeit(v.modelle[z.modell].familie, z.knoten, v.modelle[z.modell].gb).sekunden if z.laden and z.knoten else 0.0
        return Einschaetzung(sofort=True, wartezeit_s=round(laden, 1), rechner=name(z.knoten), grund=z.begruendung, vor_dir=vor_dir, wichtige=wichtige)
    if w := next((x for x in erg.wartend if x.auftrag == PROBE), None):
        return Einschaetzung(sofort=False, wartezeit_s=w.voraussichtlich_s, rechner=name(w.wartet_auf_knoten), grund=w.begruendung,
                             vor_dir=vor_dir, wichtige=wichtige)
    ab = next((x for x in erg.abgelehnt if x.auftrag == PROBE), None)
    return Einschaetzung(sofort=False, wartezeit_s=None, rechner=None, grund=ab.begruendung if ab else "unbekannt", vor_dir=vor_dir,
                         wichtige=wichtige, abgelehnt=(ab.grund or "abgelehnt") if ab else None)
