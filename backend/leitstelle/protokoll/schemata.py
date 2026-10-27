"""JSON-Schemata aller Daten, die Oberfläche und Bibliotheken sehen. Eine Wahrheit: die Pydantic-Modelle.

`python -m leitstelle.protokoll.schemata` schreibt ein Schema mit allen Modellen unter `$defs` auf die
Standardausgabe; die Oberfläche erzeugt daraus ihre Typen (frontend/werkzeuge/typen.mjs).
"""

from __future__ import annotations

import json
import sys

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from ..fach.betrieb import Freigabe
from ..fach.lagebild import Lagebild
from ..fach.regelwerk import RegelwerkAenderung, RegelwerkSicht
from ..fach.verzeichnis import AnwendungDaten, DienstAenderung, DienstDaten, Erkennung, KnotenDaten
from ..kern.modelle import Massnahme
from ..ports.ablage.eintraege import AuftragEintrag, Bewegung, Kennzahlen, KnotenEintrag, PruefEintrag, SteckbriefEintrag
from .umschlag import Umschlag

# Antworten der Leitstelle: jedes Feld wird immer mitgeschickt, auch wenn es einen Vorgabewert hat
AUSGABE: list[type[BaseModel]] = [Lagebild, AuftragEintrag, Massnahme, Erkennung, Freigabe, KnotenEintrag, PruefEintrag, Kennzahlen, Umschlag, Bewegung,
                                  RegelwerkSicht]
# Eingaben an die Leitstelle: Felder mit Vorgabewert dürfen fehlen
EINGABE: list[type[BaseModel]] = [KnotenDaten, DienstDaten, DienstAenderung, AnwendungDaten, SteckbriefEintrag, RegelwerkAenderung]


def _alle_pflicht(defs: dict, namen: set[str]) -> None:
    for name, d in defs.items():
        if name in namen and "properties" in d:
            d["required"] = list(d["properties"])


def schema() -> dict:
    paare = [(m, "serialization") for m in AUSGABE] + [(m, "validation") for m in EINGABE]
    _, defs = models_json_schema(paare, title="Leitstelle")
    _alle_pflicht(defs.get("$defs", {}), {m.__name__ for m in AUSGABE} | {"KnotenSicht", "DienstSicht", "ModellSicht", "AuftragSicht", "AnwendungSicht",
                                                                         "Meldung", "Schritt", "ModellBericht", "FremdeSicht", "FremdzugriffSicht",
                                                                         "LastSicht", "LaeuferprozessSicht", "Regelwerk", "RegelgruppeSicht",
                                                                         "RegelwertSicht", "SzenarioSicht", "Wahl"})
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Leitstelle", "type": "object",
            "properties": {m.__name__: {"$ref": f"#/$defs/{m.__name__}"} for m in AUSGABE + EINGABE}, **defs}


if __name__ == "__main__":
    json.dump(schema(), sys.stdout, ensure_ascii=False, indent=1)
