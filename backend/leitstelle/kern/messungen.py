"""Messwerk: Entscheidungen beruhen auf gemessenen Zeiten, nicht auf Annahmen.

Gemessen werden Ladezeit je Modellfamilie und Knoten, Startzeit je Dienst und Laufzeit je
Anwendung und Fähigkeit, jeweils als gleitender Mittelwert. Ohne Messung gilt ein vorsichtiger
Schätzwert, der mit der ersten Messung ersetzt wird; jede Auskunft sagt, ob sie gemessen ist.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Mittel(BaseModel):
    wert: float
    anzahl: int = 0

    def aufnehmen(self, x: float, alpha: float = 0.3) -> None:
        self.wert = x if self.anzahl == 0 else (1 - alpha) * self.wert + alpha * x
        self.anzahl += 1


class Auskunft(BaseModel):
    sekunden: float
    gemessen: bool
    anzahl: int = 0


class Messwerk(BaseModel):
    ladezeiten: dict[str, Mittel] = Field(default_factory=dict)      # "familie@knoten"
    startzeiten: dict[str, Mittel] = Field(default_factory=dict)     # dienst
    laufzeiten: dict[str, Mittel] = Field(default_factory=dict)      # "anwendung:faehigkeit"
    entladezeit_s: float = 3.0

    # ── Schätzwerte ohne Messung: lieber zu hoch als zu niedrig ──────────
    @staticmethod
    def ladezeit_schaetzung(gb: float) -> float:
        return max(5.0, gb * 0.4)

    def ladezeit(self, familie: str, knoten: str, gb: float) -> Auskunft:
        m = self.ladezeiten.get(f"{familie}@{knoten}")
        if m and m.anzahl:
            return Auskunft(sekunden=m.wert, gemessen=True, anzahl=m.anzahl)
        return Auskunft(sekunden=self.ladezeit_schaetzung(gb), gemessen=False)

    def startzeit(self, dienst: str, vorgabe_s: float) -> Auskunft:
        m = self.startzeiten.get(dienst)
        if m and m.anzahl:
            return Auskunft(sekunden=m.wert, gemessen=True, anzahl=m.anzahl)
        return Auskunft(sekunden=vorgabe_s, gemessen=False)

    def laufzeit(self, anwendung: str, faehigkeit: str) -> Auskunft:
        m = self.laufzeiten.get(f"{anwendung}:{faehigkeit}")
        if m and m.anzahl:
            return Auskunft(sekunden=m.wert, gemessen=True, anzahl=m.anzahl)
        return Auskunft(sekunden=20.0, gemessen=False)

    def rest_s(self, anwendung: str, faehigkeit: str, fortschritt_s: float) -> float:
        """Geschätzte Restzeit eines laufenden Auftrags: gemessene Laufzeit minus Fortschritt, nie unter 1 s."""
        return max(1.0, self.laufzeit(anwendung, faehigkeit).sekunden - fortschritt_s)

    # ── Aufnehmen ────────────────────────────────────────────────────────
    def merke_ladezeit(self, familie: str, knoten: str, sekunden: float) -> None:
        self.ladezeiten.setdefault(f"{familie}@{knoten}", Mittel(wert=sekunden)).aufnehmen(sekunden)

    def merke_startzeit(self, dienst: str, sekunden: float) -> None:
        self.startzeiten.setdefault(dienst, Mittel(wert=sekunden)).aufnehmen(sekunden)

    def merke_laufzeit(self, anwendung: str, faehigkeit: str, sekunden: float) -> None:
        self.laufzeiten.setdefault(f"{anwendung}:{faehigkeit}", Mittel(wert=sekunden)).aufnehmen(sekunden)
