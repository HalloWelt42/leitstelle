"""Auswerter: läuft einen Regelgraphen gegen den Verbund, ohne etwas zu verändern.

Prüft den Graph beim Speichern (ein Auslöser, bekannte Bausteine, keine Zyklen, Prüfungen
mit Ja und Nein, Aktionen mit genau einem Ausgang) und liefert je Instanz den genommenen Weg
mit Zwischenwerten; die Aktionen sind nur Beschreibungen für den Vollzug.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..messungen import Messwerk
from ..modelle import Verbund
from ..werte import Massnahmenart
from .bausteine import BAUSTEINE, Kontext


class Knoten(BaseModel):
    id: str
    art: Literal["ausloeser", "pruefung", "aktion", "ende"]
    baustein: str = ""
    parameter: dict[str, Any] = Field(default_factory=dict)
    titel: str = ""


class Kante(BaseModel):
    von: str
    nach: str
    port: Literal["ja", "nein", "aus"] = "aus"


class Regelgraph(BaseModel):
    kennung: str
    name: str
    art: Massnahmenart
    aktiv: bool = True
    fassung: int = 1
    vorlage: bool = True
    knoten: list[Knoten]
    kanten: list[Kante]

    def nach(self, von: str, port: str) -> str | None:
        for k in self.kanten:
            if k.von == von and k.port == port:
                return k.nach
        return None

    def ausloeser(self) -> Knoten | None:
        return next((k for k in self.knoten if k.art == "ausloeser"), None)

    def knoten_von(self, id: str) -> Knoten:
        return next(k for k in self.knoten if k.id == id)


class Aktion(BaseModel):
    baustein: str
    parameter: dict[str, Any] = Field(default_factory=dict)
    werte: dict[str, Any] = Field(default_factory=dict)


class Schritt(BaseModel):
    knoten: str
    baustein: str
    ergebnis: str
    werte: dict[str, Any] = Field(default_factory=dict)


class Lauf(BaseModel):
    regel: str
    art: Massnahmenart
    instanz: str
    weg: list[Schritt] = Field(default_factory=list)
    aktionen: list[Aktion] = Field(default_factory=list)
    abschluss: str = ""
    gewinn_s: float = 0.0
    aufwand_s: float = 0.0
    auftrag: str | None = None
    knoten_ziel: str | None = None
    knoten_quelle: str | None = None
    modell_ziel: str | None = None
    modelle_entladen: list[str] = Field(default_factory=list)
    werte: dict[str, Any] = Field(default_factory=dict)


def pruefen(graph: Regelgraph) -> list[str]:
    """Fehler eines Graphen in Worten; leer heißt gültig."""
    fehler: list[str] = []
    ids = {k.id for k in graph.knoten}
    if len(ids) != len(graph.knoten):
        fehler.append("doppelte Knotenkennungen")
    ausloeser = [k for k in graph.knoten if k.art == "ausloeser"]
    if len(ausloeser) != 1:
        fehler.append("genau ein Auslöser nötig")
    for k in graph.knoten:
        if k.art != "ende":
            b = BAUSTEINE.get(k.baustein)
            if b is None:
                fehler.append(f"unbekannter Baustein {k.baustein} an {k.id}")
            elif b.art != k.art:
                fehler.append(f"Baustein {k.baustein} ist {b.art}, Knoten {k.id} ist {k.art}")
        ports = {kk.port for kk in graph.kanten if kk.von == k.id}
        if k.art == "pruefung" and ports != {"ja", "nein"}:
            fehler.append(f"Prüfung {k.id} braucht genau die Ausgänge ja und nein")
        if k.art in ("ausloeser", "aktion") and ports != {"aus"}:
            fehler.append(f"{k.art} {k.id} braucht genau einen Ausgang")
        if k.art == "ende" and ports:
            fehler.append(f"Ende {k.id} darf keinen Ausgang haben")
    for kk in graph.kanten:
        if kk.von not in ids or kk.nach not in ids:
            fehler.append(f"Kante {kk.von} nach {kk.nach} zeigt ins Leere")
    # Zyklen über Tiefensuche
    nachfolger: dict[str, list[str]] = {}
    for kk in graph.kanten:
        nachfolger.setdefault(kk.von, []).append(kk.nach)
    zustand: dict[str, int] = {}

    def besuch(n: str) -> bool:
        zustand[n] = 1
        for m in nachfolger.get(n, []):
            if zustand.get(m) == 1 or (zustand.get(m) is None and besuch(m)):
                return True
        zustand[n] = 2
        return False

    for k in graph.knoten:
        if zustand.get(k.id) is None and besuch(k.id):
            fehler.append("Zyklus im Graph")
            break
    return fehler


def auswerten(graph: Regelgraph, verbund: Verbund, messwerk: Messwerk) -> list[Lauf]:
    """Ein Lauf je Instanz des Auslösers; die Schrittzahl ist durch die Knotenzahl begrenzt."""
    fehler = pruefen(graph)
    if fehler:
        raise ValueError("; ".join(fehler))
    start = graph.ausloeser()
    assert start is not None
    basis = Kontext(verbund=verbund, messwerk=messwerk)
    instanzen: list[Kontext] = BAUSTEINE[start.baustein].funktion(basis, **start.parameter)
    laeufe: list[Lauf] = []
    for kontext in instanzen:
        lauf = Lauf(regel=graph.kennung, art=graph.art, instanz=kontext.instanz, auftrag=kontext.auftrag.kennung if kontext.auftrag else None)
        lauf.weg.append(Schritt(knoten=start.id, baustein=start.baustein, ergebnis="ausgelöst", werte={"instanz": kontext.instanz}))
        aktuell = graph.nach(start.id, "aus")
        schritte = 0
        while aktuell is not None and schritte <= len(graph.knoten):
            schritte += 1
            kn = graph.knoten_von(aktuell)
            if kn.art == "ende":
                lauf.abschluss = kn.titel or kn.id
                lauf.weg.append(Schritt(knoten=kn.id, baustein="ende", ergebnis=lauf.abschluss))
                break
            b = BAUSTEINE[kn.baustein]
            if kn.art == "pruefung":
                ja = bool(b.funktion(kontext, **kn.parameter))
                lauf.weg.append(Schritt(knoten=kn.id, baustein=kn.baustein, ergebnis="ja" if ja else "nein", werte=dict(kontext.werte)))
                aktuell = graph.nach(kn.id, "ja" if ja else "nein")
            else:
                beschreibung = b.funktion(kontext, **kn.parameter)
                lauf.aktionen.append(Aktion(baustein=kn.baustein, parameter=dict(kn.parameter), werte=beschreibung))
                lauf.weg.append(Schritt(knoten=kn.id, baustein=kn.baustein, ergebnis="geplant", werte=beschreibung))
                aktuell = graph.nach(kn.id, "aus")
        lauf.gewinn_s, lauf.aufwand_s = kontext.gewinn_s, kontext.aufwand_s
        lauf.knoten_ziel, lauf.knoten_quelle, lauf.modell_ziel = kontext.knoten_ziel, kontext.knoten_quelle, kontext.modell_ziel
        lauf.modelle_entladen = list(kontext.modelle_entladen)
        lauf.werte = dict(kontext.werte)
        laeufe.append(lauf)
    return laeufe
