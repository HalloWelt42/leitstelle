"""Dienst-Adapter: Registry je Adapterart. Neue Dienstart = neues Modul plus Eintrag hier."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import httpx

from ..ablage.eintraege import Adapterart
from ..agenten import Agentenvermittlung
from .agent import AgentDienste, agent_adresse
from .openai_kompatibel import ExternOpenAI, OpenAIKompatibel
from .schnittstelle import DienstAdapter, Dienstbericht, DienstFehler, Durchleitung, ModellBericht, Strom, Verbrauch


#: Was bei jeder gesendeten Anfrage geschieht (Zählen für die Grenzen je Minute); bekommt den Modellnamen, den die Anfrage
#: nennt, oder None (Zustandsabfrage, Durchleitung ohne bekannten Namen)
BeimSenden = Callable[[str | None], None]


class AdapterFabrik(Protocol):
    """Art, Adresse, entschlüsselter Zugang und was bei jeder gesendeten Anfrage geschieht. Den Modell-Läufer spricht der
    Adapter direkt unter seiner Adresse an."""

    def __call__(self, art: Adapterart, adresse: str, zugang: str | None, beim_senden: BeimSenden | None = None) -> DienstAdapter: ...


def adapter_fabrik(verbindung_s: float = 10.0, transport: httpx.AsyncBaseTransport | None = None,
                   agenten: Agentenvermittlung | None = None) -> AdapterFabrik:
    """Baut Adapter nach Art, Adresse und (entschlüsseltem) Zugang."""
    agenten = agenten or Agentenvermittlung()

    def bauen(art: Adapterart, adresse: str, zugang: str | None, beim_senden: BeimSenden | None = None) -> DienstAdapter:
        match art:
            case Adapterart.OPENAI_KOMPATIBEL:
                return OpenAIKompatibel(adresse, zugang, verbindung_s=verbindung_s, transport=transport, beim_senden=beim_senden)
            case Adapterart.EXTERN_OPENAI:
                return ExternOpenAI(adresse, zugang, verbindung_s=verbindung_s, transport=transport, beim_senden=beim_senden)
            case Adapterart.AGENT:
                return AgentDienste(adresse, agenten, verbindung_s=verbindung_s)
        raise ValueError(f"unbekannte Adapterart {art}")

    return bauen


__all__ = ["AdapterFabrik", "BeimSenden", "Durchleitung", "agent_adresse", "DienstAdapter", "Dienstbericht", "DienstFehler", "ModellBericht", "Strom",
           "Verbrauch", "adapter_fabrik"]
