"""Bildabläufe: Registry je Art. Neue Art eines Bilddienstes = neues Modul plus Einstellung in `BildablaufEinstellung`
und ein Fall in `bildablauf`."""

from __future__ import annotations

from .comfyui import Comfy, ComfyAblauf
from .schnittstelle import SEED_GRENZE, Bildablauf, Bildauftrag, Bildergebnis, Senden

# Einstellung eines Bildablaufs; mit einer zweiten Art wird daraus eine Vereinigung, unterschieden an `art`
BildablaufEinstellung = ComfyAblauf


def bildablauf(einstellung: BildablaufEinstellung) -> Bildablauf:
    match einstellung.art:
        case "comfyui":
            return Comfy(einstellung)
    raise ValueError(f"unbekannte Art eines Bildablaufs {einstellung.art}")


__all__ = ["SEED_GRENZE", "Bildablauf", "BildablaufEinstellung", "Bildauftrag", "Bildergebnis", "ComfyAblauf", "Senden", "bildablauf"]
