"""Bildregeln: was ein Bildmodell annimmt, angewandt auf die Anfrage einer Anwendung (PROTOKOLL 6.1).

Die Regeln stehen im Bild-Steckbrief des Dienstes (Größen, Schritte, Anzahl). Kennt die Leitstelle ihn nicht (der Dienst
lief noch nie, oder er nennt keinen), gelten die Vorgabegrenzen der Fassade. Reine Funktionen; geprüft wird zweimal: vor
dem Einreihen gegen alle Bilddienste, die die Anfrage rechnen könnten (damit kein Dienst für eine Anfrage startet, die
keiner annimmt), und nach der Zuteilung gegen den einen, der rechnet, mit seinem frisch gelesenen Steckbrief.
"""

from __future__ import annotations

from ..ports.dienste.bilder import Bildauftrag
from ..protokoll.fassade import BildAnfrage, groesse_lesen
from ..protokoll.steckbrief import ANZAHL_MAX, GROESSEN_VORGABE, Bildsteckbrief
from .fehler import Ablehnung


def regeln_pruefen(s: Bildsteckbrief | None, groesse: str | None, anzahl: int, schritte: int | None) -> str | None:
    """Der Grund in einem Satz, wenn das Modell die Anfrage so nicht annimmt; sonst None."""
    if groesse is not None:
        regel = s.groessen if s and s.groessen else GROESSEN_VORGABE
        if grund := regel.pruefen(*groesse_lesen(groesse)):
            return grund + (f" Vorgabe von {s.name}: {regel.vorgabe}." if s and s.groessen else "")
    hoechstens = s.anzahl_max if s and s.anzahl_max else ANZAHL_MAX
    if anzahl > hoechstens:
        return f"Höchstens {hoechstens} Bilder je Anfrage, nicht {anzahl}."
    if schritte is not None and s and s.schritte and (grund := s.schritte.pruefen(schritte)):
        return grund
    return None


def bildauftrag(anfrage: BildAnfrage, seed: int, s: Bildsteckbrief | None) -> Bildauftrag:
    """Der Auftrag für den Bilddienst, der rechnet: ohne Größe die Vorgabe seines Modells, ohne Schritte die seines Modells
    (unbekannt: der Dienst entscheidet). Passt die Anfrage nicht, `Ablehnung` mit dem Grund `eingabe`."""
    if grund := regeln_pruefen(s, anfrage.size, anfrage.n, anfrage.steps):
        raise Ablehnung("eingabe", grund)
    breite, hoehe = groesse_lesen(anfrage.size or (s.groessen.vorgabe if s and s.groessen else GROESSEN_VORGABE.vorgabe))
    schritte = anfrage.steps if anfrage.steps is not None else (s.schritte.vorgabe if s and s.schritte else None)
    return Bildauftrag(beschreibung=anfrage.prompt, breite=breite, hoehe=hoehe, anzahl=anfrage.n, seed=seed, schritte=schritte)
