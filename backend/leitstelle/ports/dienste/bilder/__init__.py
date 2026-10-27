"""Bildabläufe: Registry je Art. Neue Art eines Bilddienstes = neues Modul plus Einstellung in `BildablaufEinstellung`
und ein Fall in `bildablauf`.

Welcher Bilddienst welchen Ablauf nutzt, entscheidet `bildablauf_waehlen` an einer Stelle: ein eigener Eintrag je Dienst
geht vor (etwa die Bildschmiede mit ComfyUI), sonst gilt die Vorgabe für alle übrigen Bilddienste (das übliche
Bildformat, wie es die Dienste des Bildwerks sprechen). So braucht ein neuer Dienst im üblichen Bildformat keinen Eintrag.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from .bildformat import Bildformat, BildformatAblauf
from .comfyui import Comfy, ComfyAblauf
from .schnittstelle import SEED_GRENZE, Bildablauf, Bildauftrag, Bildergebnis, Senden

# Einstellung eines Bildablaufs, unterschieden an `art`
BildablaufEinstellung = Annotated[ComfyAblauf | BildformatAblauf, Field(discriminator="art")]


def bildablauf(einstellung: ComfyAblauf | BildformatAblauf) -> Bildablauf:
    match einstellung.art:
        case "comfyui":
            return Comfy(einstellung)
        case "bildformat":
            return Bildformat(einstellung)
    raise ValueError(f"unbekannte Art eines Bildablaufs {einstellung.art}")


def bildablauf_waehlen(eintraege: dict[str, ComfyAblauf | BildformatAblauf], vorgabe: ComfyAblauf | BildformatAblauf | None,
                       dienst: str) -> Bildablauf | None:
    """Der Ablauf eines Bilddienstes (Kennung im Maschinenraum): eigener Eintrag, sonst die Vorgabe; None ohne beides."""
    e = eintraege.get(dienst, vorgabe)
    return bildablauf(e) if e is not None else None


__all__ = ["SEED_GRENZE", "Bildablauf", "BildablaufEinstellung", "Bildauftrag", "Bildergebnis", "BildformatAblauf", "ComfyAblauf", "Senden",
           "bildablauf", "bildablauf_waehlen"]
