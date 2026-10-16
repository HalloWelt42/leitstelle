"""Adapter für Dienste, die ein Knoten-Agent startet und anhält (Adapterart `agent`).

Jeder Prozessdienst des Agenten erscheint als ein Modell: Starten ist Laden, Anhalten ist Entladen. So gelten
Speicherplanung, Hauptregler und Oberfläche ohne Sonderweg. Geplant wird mit dem Bedarf (höchster gemessener
Wert, mindestens die Schätzung), nicht mit dem Augenblickswert: Dienste laden ihre Modelle oft erst bei Bedarf.
Ob die Selbststeuerung einen Dienst anhalten darf, sagt seine Dienstdatei; arbeitet er gerade, zählt das als
Nutzung, und er weicht nicht. Anfragen gehen weiterhin direkt an den Dienst, nicht durch die Leitstelle.
"""

from __future__ import annotations

from typing import Any

from ...protokoll.knoten import Befehl, Befehlsart, Prozesszustand
from ..agenten import AgentGetrennt, Agentenvermittlung
from .schnittstelle import Dienstbericht, DienstFehler, ModellBericht, Strom

SCHEMA = "agent://"
IM_SPEICHER = {Prozesszustand.STARTET, Prozesszustand.LAEUFT, Prozesszustand.STOPPT}


def agent_adresse(knoten: str) -> str:
    return f"{SCHEMA}{knoten}"


class AgentDienste:
    def __init__(self, adresse: str, agenten: Agentenvermittlung) -> None:
        if not adresse.startswith(SCHEMA):
            raise ValueError(f"keine Agent-Adresse: {adresse}")
        self.knoten = adresse[len(SCHEMA):]
        self.agenten = agenten

    async def zustand(self) -> Dienstbericht:
        v = self.agenten.verbindung(self.knoten)
        if v is None:
            return Dienstbericht(erreichbar=False, meldung="Maschinenraum nicht verbunden")
        modelle = [ModellBericht(schluessel=p.kennung, name=p.name, faehigkeiten=set(p.faehigkeiten), gb=p.bedarf_gb, gb_jetzt=p.gb_jetzt,
                                 parameter_mrd=None, schutz=not p.anhalten_erlaubt, aktiv=p.aktiv,
                                 geladen=p.zustand in IM_SPEICHER, instanzen=[p.kennung] if p.zustand in IM_SPEICHER else [])
                   for p in v.dienste.dienste]
        return Dienstbericht(erreichbar=True, steuerbar=True, modelle=modelle)

    async def _befehl(self, art: Befehlsart, ziel: str) -> None:
        try:
            e = await self.agenten.befehl(self.knoten, Befehl(befehl=art, ziel=ziel))
        except AgentGetrennt:
            raise DienstFehler("dienst_nicht_erreichbar", "Maschinenraum nicht verbunden", wiederholbar=True) from None
        if not e.erfolg:
            raise DienstFehler("dienst_fehler", e.meldung or "vom Maschinenraum abgelehnt")

    async def laden(self, schluessel: str) -> str:
        await self._befehl(Befehlsart.DIENST_STARTEN, schluessel)
        return schluessel

    async def entladen(self, instanz: str) -> None:
        await self._befehl(Befehlsart.DIENST_ANHALTEN, instanz)

    async def anfrage(self, pfad: str, koerper: dict[str, Any]) -> Strom:
        raise DienstFehler("nicht_unterstuetzt", "Dienste im Maschinenraum werden direkt angesprochen, nicht über die Fassade.")

    async def schliessen(self) -> None:
        return None
