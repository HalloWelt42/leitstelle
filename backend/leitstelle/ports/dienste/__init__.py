"""Dienst-Adapter: Registry je Adapterart. Neue Dienstart = neues Modul plus Eintrag hier."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from ..ablage.eintraege import Adapterart
from ..agenten import Agentenvermittlung
from .agent import AgentDienste, agent_adresse
from .openai_kompatibel import OpenAIKompatibel
from .schnittstelle import DienstAdapter, Dienstbericht, DienstFehler, Durchleitung, ModellBericht, Strom

AdapterFabrik = Callable[[Adapterart, str, str | None], DienstAdapter]


def adapter_fabrik(verbindung_s: float = 10.0, transport: httpx.AsyncBaseTransport | None = None,
                   agenten: Agentenvermittlung | None = None) -> AdapterFabrik:
    """Baut Adapter nach Art, Adresse und (entschlüsseltem) Zugang."""
    agenten = agenten or Agentenvermittlung()

    def bauen(art: Adapterart, adresse: str, zugang: str | None) -> DienstAdapter:
        match art:
            case Adapterart.OPENAI_KOMPATIBEL:
                return OpenAIKompatibel(adresse, zugang, verbindung_s=verbindung_s, transport=transport)
            case Adapterart.AGENT:
                return AgentDienste(adresse, agenten, verbindung_s=verbindung_s)
        raise ValueError(f"unbekannte Adapterart {art}")

    return bauen


__all__ = ["AdapterFabrik", "Durchleitung", "agent_adresse", "DienstAdapter", "Dienstbericht", "DienstFehler", "ModellBericht", "Strom", "adapter_fabrik"]
