"""Zahlen und Sätze für Menschen: deutsches Komma, keine Abkürzungen außer Maßeinheiten."""

from __future__ import annotations


def komma(x: float, stellen: int = 1) -> str:
    """16.25 -> '16,3' (eine Nachkommastelle, Komma)."""
    return f"{x:.{stellen}f}".replace(".", ",")


def aufzaehlung(namen: list[str], und: str = "und") -> str:
    """['A', 'B', 'C'] -> 'A, B und C'."""
    return namen[0] if len(namen) == 1 else f"{', '.join(namen[:-1])} {und} {namen[-1]}"


def schlaf_satz(namen: list[str]) -> str:
    """Was eine Anwendung hört, wenn der Rechner ihres Dienstes schläft (Grund rechner_schlaeft)."""
    if len(namen) == 1:
        return f"{namen[0]} schläft; der Auftrag kann erst laufen, wenn er wach ist."
    return f"{aufzaehlung(namen)} schlafen; der Auftrag kann erst laufen, wenn einer von ihnen wach ist."
