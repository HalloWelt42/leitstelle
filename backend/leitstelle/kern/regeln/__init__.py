"""Regelwerk als Graph: Bausteine (Registry), Vorlagen (Graphen) und Auswerter.

Eine Regel ist Daten: Knoten (Auslöser, Prüfung, Aktion, Ende) und Kanten (ja, nein, aus).
Der Auswerter läuft deterministisch, ohne Nebenwirkungen, und liefert je Instanz den
genommenen Weg mit Zwischenwerten und den geplanten Aktionen. Ausgeführt wird erst im
Umschichter nach dem Schleifenschutz.
"""

from .auswerter import Aktion, Kante, Knoten, Lauf, Regelgraph, Schritt, auswerten, pruefen
from .bausteine import BAUSTEINE, Kontext
from .graphen import VORLAGEN, vorlagen

__all__ = ["Aktion", "BAUSTEINE", "Kante", "Knoten", "Kontext", "Lauf", "Regelgraph", "Schritt", "VORLAGEN", "auswerten", "pruefen", "vorlagen"]
