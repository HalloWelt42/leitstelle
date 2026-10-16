"""Schein-Verbund: alles gemockt, nichts Echtes wird berührt.

Die Welt führt die Zeit in Sekundenschritten, lädt Modelle mit wahren (nur ihr bekannten)
Zeiten, lässt Aufträge laufen, misst und ruft die Leitstelle im Takt. Dienste, Knoten und
Anwendungen sind Attrappen mit denselben Datenmodellen wie im Betrieb.
"""

from .standard import standard_welt
from .welt import Welt

__all__ = ["Welt", "standard_welt"]
