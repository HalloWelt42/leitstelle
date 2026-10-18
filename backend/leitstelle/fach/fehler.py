"""Fachliche Ablehnung mit Grundwort (PROTOKOLL.md Abschnitt 7) und einem Satz für den Menschen."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Zusatz(BaseModel):
    """Was eine Ablehnung über Grund und Satz hinaus sagt; geht als `error.x-leitstelle` an die Anwendung."""

    rechner: list[str] = Field(default_factory=list)   # rechner_schlaeft: Namen der Rechner, auf die der Auftrag wartet


class Ablehnung(Exception):
    def __init__(self, grund: str, begruendung: str, zusatz: Zusatz | None = None) -> None:
        super().__init__(begruendung)
        self.grund = grund
        self.begruendung = begruendung
        self.zusatz = zusatz


def fehler_inhalt(grund: str, text: str, zusatz: Zusatz | None = None) -> dict[str, Any]:
    """Inhalt von `error` im Format der OpenAI-Schnittstelle: das Grundwort als `code`, der Zusatz als `x-leitstelle`."""
    inhalt: dict[str, Any] = {"message": text, "type": "leitstelle", "code": grund}
    if zusatz is not None:
        inhalt["x-leitstelle"] = zusatz.model_dump(mode="json")
    return inhalt
