"""Der Umschlag des Protokolls `leitstelle/1` (PROTOKOLL.md Abschnitt 2).

Dieselbe Form läuft intern als Ereignis, über den Kanal zur Oberfläche und später zu den Anwendungen.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

PROTOKOLL = "leitstelle/1"


def _jetzt_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


class Umschlag(BaseModel):
    protokoll: str = PROTOKOLL
    art: str
    id: str = Field(default_factory=lambda: uuid4().hex)
    zeit: str = Field(default_factory=_jetzt_iso)
    von: str = "leitstelle"
    an: str
    bezug: str | None = None
    nutzlast: dict[str, Any] = Field(default_factory=dict)


def umschlag(art: str, nutzlast: BaseModel | dict[str, Any] | None = None, an: str = "oberflaeche", bezug: str | None = None) -> Umschlag:
    """Baut einen Umschlag der Leitstelle; Pydantic-Nutzlasten werden als JSON-Daten eingelegt."""
    if isinstance(nutzlast, BaseModel):
        daten = nutzlast.model_dump(mode="json")
    else:
        daten = dict(nutzlast or {})
    return Umschlag(art=art, an=an, bezug=bezug, nutzlast=daten)
