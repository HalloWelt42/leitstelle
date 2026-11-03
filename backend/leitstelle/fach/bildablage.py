"""Bildablage (PROTOKOLL 6.3): erzeugte Bilder für ein Bildarchiv zum Abholen bereithalten.

Ist eine Anwendung ein Bildarchiv (Recht `bildarchiv` der Anwendung), legt die Leitstelle jedes Bild, das eine andere
Anwendung über `/v1/images/generations` erzeugt, mit Beschreibung, Startwert, Größe, Schritten und Modell ab. Das Archiv
holt die Bilder ab und quittiert jedes einzeln; erst dann fallen sie hier weg. Bilder, die das Archiv selbst erzeugt
hat, legt die Leitstelle nicht ab: es hat sie schon. Ohne Archiv legt sie nichts ab.

Der Platz ist begrenzt (Einstellung `bildablage_mb`); darüber fallen die ältesten wartenden Bilder weg, mit Eintrag im
Protokoll. Die Ablage stört die Antwort an die Anwendung nie: ein Fehler beim Ablegen wird nur gemeldet."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from pathlib import Path

from ..ports.ablage.eintraege import AnwendungEintrag, BildablageEintrag
from ..ports.ablage.repositorien import BildablageAblage
from ..ports.dienste.bilder.schnittstelle import Bildauftrag, Bildergebnis

log = logging.getLogger("leitstelle.bildablage")


def ist_archiv(a: AnwendungEintrag) -> bool:
    return a.bildarchiv and not a.gesperrt


class Bildablage:
    def __init__(self, ablage: BildablageAblage, ordner: Path, grenze_mb: int) -> None:
        self.ablage, self.ordner, self.grenze_mb = ablage, ordner, grenze_mb

    def _datei(self, kennung: str) -> Path:
        return self.ordner / f"{kennung}.png"

    async def ablegen(self, erzeuger: AnwendungEintrag, anwendungen: Iterable[AnwendungEintrag], auftrag: str, bild: Bildauftrag,
                      ergebnis: Bildergebnis, familie: str, jetzt_s: float) -> int:
        """Die Bilder eines Ergebnisses ablegen, wenn es ein Archiv gibt und der Erzeuger nicht selbst eines ist.
        Gibt zurück, wie viele abgelegt wurden; Fehler werden gemeldet, nie weitergereicht."""
        if ist_archiv(erzeuger) or not any(ist_archiv(a) for a in anwendungen):
            return 0
        abgelegt = 0
        try:
            self.ordner.mkdir(parents=True, exist_ok=True)
            for nummer, daten in enumerate(ergebnis.bilder):
                kennung = uuid.uuid4().hex
                ziel = self._datei(kennung)
                zwischen = ziel.with_suffix(".teil")
                zwischen.write_bytes(daten)
                zwischen.replace(ziel)
                await self.ablage.speichern(BildablageEintrag(
                    kennung=kennung, anwendung=erzeuger.kennung, auftrag=auftrag, familie=familie, beschreibung=bild.beschreibung,
                    seed=ergebnis.seed, breite=bild.breite, hoehe=bild.hoehe, schritte=ergebnis.schritte, nummer=nummer,
                    bytes=len(daten), erzeugt_s=jetzt_s))
                abgelegt += 1
            await self._begrenzen()
        except Exception as fehler:          # die Antwort an die Anwendung geht vor; die Ablage meldet nur
            log.warning("Bild aus Auftrag %s nicht abgelegt: %s", auftrag, fehler)
        return abgelegt

    async def _begrenzen(self) -> None:
        grenze = self.grenze_mb * 1024 * 1024
        _, belegt = await self.ablage.summe()
        while belegt > grenze:
            alt = await self.ablage.aelteste(20)
            if not alt:
                return
            for e in alt:
                if belegt <= grenze:
                    return
                await self.quittieren(e.kennung)
                belegt -= e.bytes
                log.warning("Bildablage voll (%d MB): ältestes Bild %s aus Auftrag %s ohne Abholung entfernt",
                            self.grenze_mb, e.kennung, e.auftrag)

    async def wartend(self, anzahl: int) -> tuple[list[BildablageEintrag], int, int]:
        """Die ältesten wartenden Bilder, dazu Anzahl und Bytes aller wartenden."""
        alle, belegt = await self.ablage.summe()
        return await self.ablage.aelteste(anzahl), alle, belegt

    async def datei(self, kennung: str) -> tuple[BildablageEintrag, bytes] | None:
        e = await self.ablage.holen(kennung)
        if e is None or not self._datei(kennung).is_file():
            return None
        return e, self._datei(kennung).read_bytes()

    async def quittieren(self, kennung: str) -> bool:
        e = await self.ablage.holen(kennung)
        self._datei(kennung).unlink(missing_ok=True)
        await self.ablage.loeschen(kennung)
        return e is not None
