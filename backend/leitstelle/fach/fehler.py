"""Fachliche Ablehnung mit Grundwort (PROTOKOLL.md Abschnitt 7) und einem Satz für den Menschen."""

from __future__ import annotations


class Ablehnung(Exception):
    def __init__(self, grund: str, begruendung: str) -> None:
        super().__init__(begruendung)
        self.grund = grund
        self.begruendung = begruendung
