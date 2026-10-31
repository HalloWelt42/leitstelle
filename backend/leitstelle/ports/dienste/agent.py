"""Adapter für Dienste, die ein Knoten-Agent startet und anhält (Adapterart `agent`).

Jeder Prozessdienst des Agenten erscheint als ein Modell: Starten ist Laden, Anhalten ist Entladen. So gelten
Speicherplanung, Hauptregler und Oberfläche ohne Sonderweg. Geplant wird mit dem Bedarf (höchster gemessener
Wert, mindestens die Schätzung), nicht mit dem Augenblickswert: Dienste laden ihre Modelle oft erst bei Bedarf.
Ob die Selbststeuerung einen Dienst anhalten darf, sagt seine Dienstdatei; arbeitet er gerade, zählt das als
Nutzung, und er weicht nicht. Anfragen gehen weiterhin direkt an den Dienst, nicht durch die Leitstelle.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from ...protokoll.knoten import Befehl, Befehlsart, Prozesszustand
from ..agenten import AgentGetrennt, Agentenvermittlung
from .openai_kompatibel import HttpStrom
from .schnittstelle import Dienstbericht, DienstFehler, Durchleitung, ModellBericht, Strom

SCHEMA = "agent://"
IM_SPEICHER = {Prozesszustand.STARTET, Prozesszustand.LAEUFT, Prozesszustand.STOPPT}


def agent_adresse(knoten: str) -> str:
    return f"{SCHEMA}{knoten}"


class AgentDienste:
    meldet_sich_selbst = True            # der Maschinenraum meldet sich; sein Zustand liegt schon vor
    ueberlast_status = frozenset({429})

    def __init__(self, adresse: str, agenten: Agentenvermittlung, verbindung_s: float = 10.0) -> None:
        if not adresse.startswith(SCHEMA):
            raise ValueError(f"keine Agent-Adresse: {adresse}")
        self.knoten = adresse[len(SCHEMA):]
        self.agenten = agenten
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(connect=verbindung_s, read=None, write=None, pool=None))

    async def zustand(self) -> Dienstbericht:
        v = self.agenten.verbindung(self.knoten)
        if v is None:
            return Dienstbericht(erreichbar=False, meldung="Maschinenraum nicht verbunden")
        modelle = [ModellBericht(schluessel=p.kennung, name=p.name, faehigkeiten=set(p.faehigkeiten), gb=p.bedarf_gb, gb_jetzt=p.gb_jetzt,
                                 parameter_mrd=None, schutz=not p.anhalten_erlaubt, aktiv=p.aktiv, plaetze=p.plaetze, selbstauskunft=p.selbstauskunft, familie=p.instanz_von, instanzen_hoechstens=p.instanzen,
                                 geladen=p.zustand in IM_SPEICHER, instanzen=[p.kennung] if p.zustand in IM_SPEICHER else [], sperre=p.sperre)
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

    async def instanz_laden(self, schluessel: str, stufe: int) -> str:
        """Weitere Instanz eines Dienstes: der Maschinenraum startet sie unter `<kennung>.<stufe>` mit eigenem Port."""
        return await self.laden(f"{schluessel}.{stufe}")

    async def entladen(self, instanz: str) -> None:
        await self._befehl(Befehlsart.DIENST_ANHALTEN, instanz)

    async def anfrage(self, pfad: str, koerper: dict[str, Any]) -> Strom:
        return await self.durchleiten("", Durchleitung(methode="POST", pfad=pfad, kopf={"content-type": "application/json"},
                                                       inhalt=json.dumps(koerper).encode()))

    async def durchleiten(self, schluessel: str, d: Durchleitung) -> Strom:
        """Über die Durchleitung des Maschinenraums an den Dienst `schluessel`; Ziel ist die Adresse, von der sich der
        Maschinenraum verbunden hat, mit seinem eigenen Schlüssel."""
        v = self.agenten.verbindung(self.knoten)
        basis = v.durchleitung if v else None
        if v is None or basis is None:
            raise DienstFehler("dienst_nicht_erreichbar", "Maschinenraum nicht verbunden oder ohne Durchleitung", wiederholbar=True)
        url = httpx.URL(f"{basis}/{schluessel}/{d.pfad.lstrip('/')}", query=d.abfrage.encode())
        kopf = {**d.kopf, "authorization": f"Bearer {v.schluessel}"}
        try:
            antwort = await self._client.send(self._client.build_request(d.methode, url, headers=kopf, content=d.inhalt), stream=True)
        except httpx.HTTPError as fehler:
            raise DienstFehler("dienst_nicht_erreichbar", f"Durchleitung: {type(fehler).__name__} {fehler}".strip(), wiederholbar=True) from fehler
        return HttpStrom(antwort)

    async def schliessen(self) -> None:
        await self._client.aclose()
