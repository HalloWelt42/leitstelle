"""Speicherplaner: passt ein Modell auf einen Knoten, und was müsste dafür weichen?

Reine Funktion über den Verbund. Regeln (aus txt2voice und Zusage zusammengeführt):
Budget je Knoten; nie entladen: geschützte Modelle (unter der Schutzgrenze oder Einbettung),
rechnende Modelle, Modelle mit wartenden Aufträgen, Modelle, die eine begonnene Arbeit einer Anwendung
gerade nutzt (außer für diese Arbeit selbst), Modelle innerhalb der Mindestverweildauer;
nur so viel wie nötig, größte zuerst; Leerlauf-Entladen nur, wenn Platz gebraucht wird.
Der Plan ist zugleich die Vorschau ("Speicher freigeben").
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .messungen import Messwerk
from .modelle import Modell, Verbund
from .werte import Modellzustand
from .text import komma


class Speicherplan(BaseModel):
    knoten: str
    benoetigt_gb: float
    frei_gb: float
    passt: bool
    entladen: list[str] = Field(default_factory=list)       # Modellkennungen, größte zuerst
    frei_nach_s: float | None = None                         # wann es ohne Entladen passen würde
    blockiert_durch: list[str] = Field(default_factory=list)  # rechnende Modelle, die den Platz halten
    aufwand_s: float = 0.0                                   # Entladen plus Laden, aus Messung oder Schätzung
    begruendung: str = ""


def entladbar(verbund: Verbund, m: Modell, jetzt: float, nur_leerlauf: bool, leerlauf_grenze_s: float | None = None,
              fuer_arbeit: str | None = None) -> tuple[bool, str]:
    """Ob ein Modell weichen darf, mit Grund, warum nicht. `fuer_arbeit`: die Arbeit, für die Platz gebraucht wird."""
    r = verbund.regelwerk
    if m.zustand != Modellzustand.GELADEN or verbund.belegung(m.kennung):
        return False, "rechnet, lädt oder ist schon zugeteilt"
    if m.geschuetzt(r.schutzgrenze_mrd):
        return False, "geschützt (vom Dienst vorgegeben, unter der Schutzgrenze oder Einbettung)"
    if verbund.wartende_auf_familie(m.familie):
        return False, "ein Auftrag wartet darauf"
    if (w := verbund.arbeit_haelt(m.kennung, ausser=fuer_arbeit)) is not None:
        return False, f"die begonnene Arbeit {w.titel} nutzt es (zuletzt vor {jetzt - w.modelle[m.kennung]:.0f} s)"
    if m.geladen_seit_s is not None and jetzt - m.geladen_seit_s < r.mindestverweildauer_s:
        return False, "Mindestverweildauer läuft noch"
    grenze = r.leerlauf_s if leerlauf_grenze_s is None else leerlauf_grenze_s
    if nur_leerlauf and m.letzte_nutzung_s is not None and jetzt - m.letzte_nutzung_s < grenze:
        return False, f"wurde vor {jetzt - m.letzte_nutzung_s:.0f} s zuletzt genutzt (Frist {grenze:.0f} s)"
    return True, "darf weichen"


def planen(verbund: Verbund, knoten: str, benoetigt_gb: float, messwerk: Messwerk, familie: str | None = None, nur_leerlauf: bool = False,
           leerlauf_grenze_s: float | None = None, fuer_arbeit: str | None = None) -> Speicherplan:
    """Plant, ob benoetigt_gb auf dem Knoten Platz findet; entlädt nur so viel wie nötig, größte zuerst."""
    jetzt = verbund.zeit_s
    frei = verbund.frei_gb(knoten)
    ladezeit = messwerk.ladezeit(familie, knoten, benoetigt_gb).sekunden if familie else messwerk.ladezeit_schaetzung(benoetigt_gb)
    if benoetigt_gb <= frei:
        return Speicherplan(knoten=knoten, benoetigt_gb=benoetigt_gb, frei_gb=frei, passt=True, aufwand_s=ladezeit,
                            begruendung=f"{komma(benoetigt_gb)} GB passen, {komma(frei)} GB frei")
    kandidaten = sorted((m for m in verbund.modelle_auf(knoten) if entladbar(verbund, m, jetzt, nur_leerlauf, leerlauf_grenze_s, fuer_arbeit)[0]), key=lambda m: m.gb, reverse=True)
    entladen: list[str] = []
    gewonnen = 0.0
    for m in kandidaten:
        if frei + gewonnen >= benoetigt_gb:
            break
        entladen.append(m.kennung)
        gewonnen += m.gb
    if frei + gewonnen >= benoetigt_gb:
        namen = ", ".join(verbund.modelle[k].name for k in entladen)
        return Speicherplan(knoten=knoten, benoetigt_gb=benoetigt_gb, frei_gb=frei, passt=True, entladen=entladen,
                            aufwand_s=ladezeit + messwerk.entladezeit_s * len(entladen),
                            begruendung=f"passt nach Entladen von {namen} ({komma(gewonnen)} GB)")
    # Passt nicht: wann würde es? Wenn rechnende Modelle fertig sind und weichen könnten.
    rechnende = [m for m in verbund.modelle_auf(knoten) if m.im_speicher and verbund.belegung(m.kennung) and not m.geschuetzt(verbund.regelwerk.schutzgrenze_mrd)]
    frei_nach = None
    blockiert = []
    for m in sorted(rechnende, key=lambda m: m.gb, reverse=True):
        rest = max((messwerk.rest_s(a.anwendung, a.faehigkeit.value, a.fortschritt_s) for a in verbund.belegung(m.kennung)), default=0.0)
        blockiert.append(m.kennung)
        if frei + gewonnen + m.gb >= benoetigt_gb:
            frei_nach = rest
            break
    gruende = "; ".join(f"{m.name}: {entladbar(verbund, m, jetzt, nur_leerlauf, leerlauf_grenze_s, fuer_arbeit)[1]}" for m in verbund.modelle_auf(knoten) if m.im_speicher and m.kennung not in entladen)
    return Speicherplan(knoten=knoten, benoetigt_gb=benoetigt_gb, frei_gb=frei, passt=False, entladen=[], frei_nach_s=frei_nach, blockiert_durch=blockiert,
                        aufwand_s=ladezeit, begruendung=f"{komma(benoetigt_gb)} GB passen nicht neben {komma(verbund.geladen_gb(knoten))} GB ({komma(frei)} GB frei). {gruende}")
