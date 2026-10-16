"""Gemeinsame Hilfen: Standard-Welt (alles gemockt), Zugriffe, Zustände einstellen."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from leitstelle.kern.modelle import Regelwerk  # noqa: E402
from leitstelle.kern.werte import Massnahmenart, Massnahmenzustand, Modellzustand  # noqa: E402
from leitstelle.simulation import Welt, standard_welt  # noqa: E402


@pytest.fixture
def welt() -> Welt:
    return standard_welt()


def welt_mit(**regeln) -> Welt:
    return standard_welt(Regelwerk(**regeln))


def ausgefuehrt(w: Welt, art: Massnahmenart | None = None):
    return [m for m in w.verbund.massnahmen if m.zustand == Massnahmenzustand.AUSGEFUEHRT and (art is None or m.art == art)]


def gesperrt(w: Welt):
    return [m for m in w.verbund.massnahmen if m.zustand == Massnahmenzustand.GESPERRT]


def abschluesse(w: Welt, regel: str) -> set[str]:
    """Letzte Schrittergebnisse der Läufe einer Regel (Ende-Titel) - zum Prüfen der Zweige."""
    aus = set()
    for m in w.verbund.massnahmen:
        if m.regel == regel:
            aus.add(m.schritte[-1].split(": ", 1)[-1] if m.schritte else "")
    return aus


def lade(w: Welt, modell: str, vor_s: float = 100000.0) -> None:
    """Setzt ein Modell als geladen und lange ungenutzt."""
    m = w.verbund.modelle[modell]
    m.zustand = Modellzustand.GELADEN
    m.geladen_seit_s = w.verbund.zeit_s - vor_s
    m.letzte_nutzung_s = w.verbund.zeit_s - vor_s


def entlade(w: Welt, modell: str) -> None:
    m = w.verbund.modelle[modell]
    m.zustand = Modellzustand.FREI
    m.geladen_seit_s = None
