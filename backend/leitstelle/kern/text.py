"""Zahlen in Sätzen für Menschen: deutsches Komma, keine Abkürzungen außer Maßeinheiten."""

from __future__ import annotations


def komma(x: float, stellen: int = 1) -> str:
    """16.25 -> '16,3' (eine Nachkommastelle, Komma)."""
    return f"{x:.{stellen}f}".replace(".", ",")
