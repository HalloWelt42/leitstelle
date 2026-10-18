"""Die Leitstelle als Takt: Lage beurteilen, zuteilen, umschichten.

Reine Orchestrierung über Verbund, Messwerk und einen Vollzug. Keine Ein- und Ausgabe; der
Schein-Verbund und später die Adapter liefern den Vollzug.
"""

from __future__ import annotations

from .lage import beurteilen
from .messungen import Messwerk
from .modelle import Verbund
from .regeln.auswerter import Regelgraph
from .regeln.graphen import vorlagen
from .umschichter import Umschichter, Vollzug
from .werte import Auftragszustand, Lage
from .zuteiler import zuteilen


class Leitstelle:
    def __init__(self, graphen: list[Regelgraph] | None = None) -> None:
        self.umschichter = Umschichter(graphen if graphen is not None else vorlagen())
        self.lage: Lage = Lage.RUHIG
        self.lage_grund: str = ""

    def takt(self, verbund: Verbund, messwerk: Messwerk, vollzug: Vollzug) -> None:
        """Voller Takt: zuteilen (beurteilt die Lage), umschichten, erneut zuteilen."""
        self.zuteilen(verbund, messwerk, vollzug)
        self.umschichter.takt(verbund, messwerk, vollzug)
        # Nach Maßnahmen können Aufträge sofort zuteilbar sein (zum Beispiel nach Entladen)
        self.zuteilen(verbund, messwerk, vollzug)

    def zuteilen(self, verbund: Verbund, messwerk: Messwerk, vollzug: Vollzug) -> None:
        """Nur zuteilen (ohne Umschichtung), zum Beispiel sofort nach einem neuen Auftrag oder einem Ende."""
        self.lage, self.lage_grund = beurteilen(verbund)
        ergebnis = zuteilen(verbund, messwerk)
        for z in ergebnis.zuteilungen:
            a = verbund.auftraege[z.auftrag]
            a.dienst, a.modell, a.knoten = z.dienst, z.modell, z.knoten
            a.zustand = Auftragszustand.ZUGETEILT
            a.begruendung = z.begruendung
            a.wartet_auf_familie = a.wartet_auf_knoten = None
            a.voraussichtlich_s = None
            a.extern = verbund.dienste[z.dienst].extern
            if z.laden:
                vollzug.modell_laden(z.modell)
                self.umschichter.merke_bewegung("laden", verbund.modelle[z.modell].familie, z.knoten, verbund.zeit_s)
        for w in ergebnis.wartend:
            a = verbund.auftraege[w.auftrag]
            if a.zustand != w.zustand:
                a.zustand = w.zustand
            a.begruendung = w.begruendung
            a.wartet_auf_familie = w.wartet_auf_familie
            a.wartet_auf_knoten = w.wartet_auf_knoten
            a.voraussichtlich_s = w.voraussichtlich_s
        for w in ergebnis.abgelehnt:
            a = verbund.auftraege[w.auftrag]
            a.zustand = Auftragszustand.ABGELEHNT
            a.begruendung = w.begruendung
            a.grund = w.grund
            a.schlafende_knoten = list(w.schlafende_knoten)
            verbund.melden(f"abgelehnt {a.kennung}: {w.begruendung}")
