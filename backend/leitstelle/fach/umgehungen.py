"""Am Leitstand vorbei (`knoten.fremde`, PROTOKOLL 4.2): was der Maschinenraum eines Rechners an Zugriffen auf seine
Modelle sieht, die nicht über die Leitstelle gehen, und wie die Leitstelle sie deutet. Eine Stelle für Lagebild und
Meldungen.

Die Leitstelle spricht den Modell-Läufer eines Rechners direkt an. Eine Verbindung zum Läufer aus dem Netz von der
Adresse der Leitstelle ist darum, solange sie einen Läufer dieses Rechners eingetragen hat, vermutlich sie selbst; sonst
ist es ein anderes Programm auf ihrem Rechner. Alles andere ist eine Umgehung.

Gemeldet wird jede Umgehung einmal, wenn sie auftaucht, und einmal, wenn sie verschwunden ist. Damit ein Programm, das
den Läufer immer wieder kurz anspricht, nicht bei jedem Takt neu erscheint, gilt eine Umgehung erst nach dem Nachlauf als
verschwunden. Ohne Beobachtung (`beobachtet` falsch) sagt die Liste nichts; dann verschwindet auch nichts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..kern.text import komma
from ..protokoll.knoten import Fremdart, Fremdzugriff, Fremdzugriffe

Schluessel = tuple[str, str, int | None]


class Fremddeutung(str, Enum):
    UMGEHUNG = "umgehung"                               # Programm auf dem Rechner oder Gegenstelle im Netz
    RECHNER_DER_LEITSTELLE = "rechner_der_leitstelle"   # anderes Programm auf dem Rechner der Leitstelle (sie hat dort keinen Läufer eingetragen)
    LEITSTELLE_DIREKT = "leitstelle_direkt"             # vermutlich die Leitstelle selbst (sie spricht den Läufer direkt an): keine Umgehung


def schluessel(z: Fremdzugriff) -> Schluessel:
    """Derselbe Zugriff über mehrere Meldungen: Art, wer und Prozess."""
    return z.art.value, z.wer, z.pid


def deuten(z: Fremdzugriff, laeufer_direkt: bool) -> Fremddeutung:
    if z.art == Fremdart.LAEUFER and z.vom_rechner_der_leitstelle:
        return Fremddeutung.LEITSTELLE_DIREKT if laeufer_direkt else Fremddeutung.RECHNER_DER_LEITSTELLE
    return Fremddeutung.UMGEHUNG


def umgehungen(f: Fremdzugriffe, laeufer_direkt: bool) -> list[Fremdzugriff]:
    """Was wirklich am Leitstand vorbeigeht: alle Zugriffe ohne die Leitstelle selbst auf dem direkten Weg."""
    return [z for z in f.zugriffe if deuten(z, laeufer_direkt) != Fremddeutung.LEITSTELLE_DIREKT] if f.beobachtet else []


def _wer(z: Fremdzugriff, deutung: Fremddeutung) -> str:
    wo = [f"Prozess {z.pid}"] if z.pid else []
    if z.ordner:
        wo.append(z.ordner)
    if deutung == Fremddeutung.RECHNER_DER_LEITSTELLE:
        wo.append("anderes Programm auf dem Rechner der Leitstelle")
    return f"{z.wer} ({', '.join(wo)})" if wo else z.wer


def beschreibung(z: Fremdzugriff, deutung: Fremddeutung) -> str:
    """Satzteil für die Meldung, wenn eine Umgehung auftaucht."""
    if z.art == Fremdart.SPEICHER:
        return f"{_wer(z, deutung)} belegt {komma(z.gb or 0.0)} GB außerhalb von Diensten und Läufer"
    return f"{_wer(z, deutung)} spricht den Modell-Läufer direkt an"


def kurz(z: Fremdzugriff) -> str:
    """Wer, für die Meldung, wenn eine Umgehung verschwunden ist."""
    return f"{z.wer} (Prozess {z.pid})" if z.pid else z.wer


@dataclass
class Umgehungsbuch:
    """Welche Umgehungen je Rechner gemeldet sind und wann sie zuletzt gesehen wurden."""

    nachlauf_s: float
    _gesehen: dict[str, dict[Schluessel, tuple[Fremdzugriff, float]]] = field(default_factory=dict)

    def abgleichen(self, knoten: str, jetzt: list[Fremdzugriff], zeit_s: float) -> tuple[list[Fremdzugriff], list[Fremdzugriff]]:
        """Die gerade gesehenen Umgehungen eintragen; liefert die neuen und die, die seit dem Nachlauf fehlen."""
        buch = self._gesehen.setdefault(knoten, {})
        neu = [z for z in jetzt if schluessel(z) not in buch]
        for z in jetzt:
            buch[schluessel(z)] = (z, zeit_s)
        da = {schluessel(z) for z in jetzt}
        weg = [s for s, (_, gesehen_s) in buch.items() if s not in da and zeit_s - gesehen_s >= self.nachlauf_s]
        return neu, [buch.pop(s)[0] for s in weg]

    def am_laeufer(self, knoten: str) -> list[Fremdzugriff]:
        """Die gemeldeten Umgehungen am Läufer des Rechners, die noch gelten (auch im Nachlauf); für die Regel "Läufer
        arbeitet ohne Auftrag": wer so am Läufer hängt, erklärt, warum ein Arbeiter ohne Auftrag der Leitstelle rechnet."""
        return [z for z, _ in self._gesehen.get(knoten, {}).values() if z.art == Fremdart.LAEUFER]

    def vergessen(self, knoten: str) -> None:
        """Der Maschinenraum ist weg: was er gesehen hat, gilt nicht mehr (beim nächsten Verbinden wird neu gemeldet)."""
        self._gesehen.pop(knoten, None)
