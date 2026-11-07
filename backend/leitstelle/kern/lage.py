"""Lagebeurteilung: ruhig, angespannt, engpass, mit Begründung.

Ein schlafender Rechner ist kein Ausfall: er zählt weder als nicht erreichbar noch als Knoten mit offenen Aufträgen
(die Apps warten selbst, bis er wach ist). Er steht nur als Hinweis in der Begründung, "MacBook M4 Max 128 GB schläft".
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


def knoten_beurteilen(verbund: Verbund, knoten: str) -> tuple[Lage, str]:
    """Lage eines einzelnen Rechners (Nutzer 07.11.2026: "Auslastung zählt pro Rechner, weil diese sich nie gegenseitig
    beeinflussen"): Engpass, wenn er mit offenen Aufträgen nicht erreichbar ist oder zwei Aufträge auf seinen Speicher
    warten; angespannt bei einem wartenden Auftrag; sonst ruhig. Was auf einem anderen Rechner geschieht, zählt nie."""
    k = verbund.knoten[knoten]
    if k.schlaeft:
        return Lage.RUHIG, f"{k.name} schläft"
    if not k.erreichbar and any(a.knoten == knoten and a.offen for a in verbund.auftraege.values()):
        return Lage.ENGPASS, f"{k.name} mit offenen Aufträgen nicht erreichbar"
    warten = [a for a in verbund.auftraege.values() if a.zustand == Auftragszustand.WARTET_SPEICHER and a.wartet_auf_knoten == knoten]
    if len(warten) >= 2:
        return Lage.ENGPASS, f"{len(warten)} Aufträge warten auf Speicher auf {k.name}"
    if warten:
        return Lage.ANGESPANNT, f"ein Auftrag wartet auf Speicher auf {k.name}"
    return Lage.RUHIG, f"auf {k.name} wartet niemand auf Speicher"
