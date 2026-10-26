"""Dienst-Adapter: Registry je Adapterart. Neue Dienstart = neues Modul plus Eintrag hier."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import httpx

from ..ablage.eintraege import Adapterart
from ..agenten import Agentenvermittlung
from .agent import AgentDienste, agent_adresse
from .laeuferweg import UeberMaschinenraum
from .openai_kompatibel import ExternOpenAI, OpenAIKompatibel
from .schnittstelle import DienstAdapter, Dienstbericht, DienstFehler, Durchleitung, ModellBericht, Strom


class AdapterFabrik(Protocol):
    """Art, Adresse, entschlüsselter Zugang, was bei jeder gesendeten Anfrage geschieht (Zählen für die Grenze je Minute)
    und, nur beim Modell-Läufer, der Rechner, über dessen Maschinenraum der Weg geht (None: direkt an die Adresse)."""

    def __call__(self, art: Adapterart, adresse: str, zugang: str | None, beim_senden: Callable[[], None] | None = None,
                 maschinenraum: str | None = None) -> DienstAdapter: ...


def adapter_fabrik(verbindung_s: float = 10.0, transport: httpx.AsyncBaseTransport | None = None,
                   agenten: Agentenvermittlung | None = None) -> AdapterFabrik:
    """Baut Adapter nach Art, Adresse und (entschlüsseltem) Zugang."""
    agenten = agenten or Agentenvermittlung()

    def bauen(art: Adapterart, adresse: str, zugang: str | None, beim_senden: Callable[[], None] | None = None,
              maschinenraum: str | None = None) -> DienstAdapter:
        if maschinenraum is not None and art != Adapterart.OPENAI_KOMPATIBEL:
            raise ValueError(f"über den Maschinenraum geht nur der Modell-Läufer, nicht {art.value}")
        match art:
            case Adapterart.OPENAI_KOMPATIBEL:
                weg = UeberMaschinenraum(maschinenraum, agenten, innen=transport) if maschinenraum else transport
                return OpenAIKompatibel(adresse, zugang, verbindung_s=verbindung_s, transport=weg, beim_senden=beim_senden)
            case Adapterart.EXTERN_OPENAI:
                return ExternOpenAI(adresse, zugang, verbindung_s=verbindung_s, transport=transport, beim_senden=beim_senden)
            case Adapterart.AGENT:
                return AgentDienste(adresse, agenten, verbindung_s=verbindung_s)
        raise ValueError(f"unbekannte Adapterart {art}")

    return bauen


__all__ = ["AdapterFabrik", "Durchleitung", "agent_adresse", "DienstAdapter", "Dienstbericht", "DienstFehler", "ModellBericht", "Strom", "adapter_fabrik"]
