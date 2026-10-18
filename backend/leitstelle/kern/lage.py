"""Lagebeurteilung: ruhig, angespannt, engpass, mit Begründung.

Ein schlafender Rechner ist kein Ausfall: er zählt weder als nicht erreichbar noch als Knoten mit offenen Aufträgen
(die Apps warten selbst, bis er wach ist). Er steht nur als Hinweis in der Begründung, "Mac Studio schläft".
"""

from __future__ import annotations

from .modelle import Verbund
from .text import aufzaehlung
from .werte import Auftragszustand, Lage


def _mit_schlaf(verbund: Verbund, satz: str) -> str:
    schlafend = [k.name for k in verbund.knoten.values() if k.schlaeft]
    if not schlafend:
        return satz
    return f"{satz}; {aufzaehlung(schlafend)} {'schläft' if len(schlafend) == 1 else 'schlafen'}"


def beurteilen(verbund: Verbund) -> tuple[Lage, str]:
    lage, satz = _beurteilen(verbund)
    return lage, _mit_schlaf(verbund, satz)


def _beurteilen(verbund: Verbund) -> tuple[Lage, str]:
    gruende: list[str] = []
    wach = [k for k in verbund.knoten.values() if not k.schlaeft]
    wartet_speicher = [a for a in verbund.auftraege.values() if a.zustand == Auftragszustand.WARTET_SPEICHER]
    ausgefallen = [k for k in wach if not k.erreichbar and any(a.knoten == k.kennung and a.offen for a in verbund.auftraege.values())]
    voll = [k for k in wach if k.erreichbar and verbund.belegt_anteil(k.kennung) >= verbund.regelwerk.speicher_warnschwelle and verbund.modelle_auf(k.kennung)]
    if ausgefallen:
        gruende.append("Knoten mit offenen Aufträgen nicht erreichbar: " + ", ".join(k.name for k in ausgefallen))
    if len(wartet_speicher) >= 2:
        gruende.append(f"{len(wartet_speicher)} Aufträge warten auf Speicher")
    if ausgefallen or len(wartet_speicher) >= 2:
        return Lage.ENGPASS, "; ".join(gruende)
    nicht_erreichbar = [k for k in wach if not k.erreichbar]
    if wartet_speicher:
        gruende.append("ein Auftrag wartet auf Speicher")
        if voll:
            gruende.append("Speicher knapp auf " + ", ".join(f"{k.name} ({verbund.belegt_anteil(k.kennung) * 100:.0f} Prozent)" for k in voll))
    if nicht_erreichbar:
        gruende.append("nicht erreichbar: " + ", ".join(k.name for k in nicht_erreichbar))
    if gruende:
        return Lage.ANGESPANNT, "; ".join(gruende)
    if voll:
        return Lage.RUHIG, "Speicher gut gefüllt auf " + ", ".join(k.name for k in voll) + ", aber niemand wartet"
    if len(wach) < len(verbund.knoten):
        return Lage.RUHIG, "alle wachen Knoten erreichbar, keine Wartezeiten" if wach else "keine Wartezeiten"
    return Lage.RUHIG, "alle Knoten erreichbar, keine Wartezeiten"
