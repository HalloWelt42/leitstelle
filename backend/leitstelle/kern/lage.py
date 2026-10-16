"""Lagebeurteilung: ruhig, angespannt, engpass, mit Begründung."""

from __future__ import annotations

from .modelle import Verbund
from .werte import Auftragszustand, Lage


def beurteilen(verbund: Verbund) -> tuple[Lage, str]:
    gruende: list[str] = []
    wartet_speicher = [a for a in verbund.auftraege.values() if a.zustand == Auftragszustand.WARTET_SPEICHER]
    ausgefallen = [k for k in verbund.knoten.values() if not k.erreichbar and any(a.knoten == k.kennung and a.offen for a in verbund.auftraege.values())]
    voll = [k for k in verbund.knoten.values() if k.erreichbar and verbund.belegt_anteil(k.kennung) >= verbund.regelwerk.speicher_warnschwelle and verbund.modelle_auf(k.kennung)]
    if ausgefallen:
        gruende.append("Knoten mit offenen Aufträgen nicht erreichbar: " + ", ".join(k.name for k in ausgefallen))
    if len(wartet_speicher) >= 2:
        gruende.append(f"{len(wartet_speicher)} Aufträge warten auf Speicher")
    if ausgefallen or len(wartet_speicher) >= 2:
        return Lage.ENGPASS, "; ".join(gruende)
    nicht_erreichbar = [k for k in verbund.knoten.values() if not k.erreichbar]
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
    return Lage.RUHIG, "alle Knoten erreichbar, keine Wartezeiten"
