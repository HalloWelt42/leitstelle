"""Last des Modell-Läufers und des Rechners (ZUSAMMENSPIEL Z6): wann ein Arbeiter des Läufers ohne Auftrag rechnet,
wie viel die Leitstelle gerade auf dem Läufer arbeitet, die Fremdlast im Mittel und Sätze dazu. Eine Stelle für Regeln,
Lagebild und Verlauf; gemessen hat der Maschinenraum (knoten.last), entschieden wird hier.

Ein Arbeiter rechnet ohne Auftrag, wenn er seit der Frist (`laeufer_frist_s`) in jeder Messung mindestens die Schwelle
(`laeufer_schwelle_prozent`, Prozent eines Kerns) rechnet und in diesem Fenster kein Auftrag der Leitstelle auf einem
Modell eines Läufers dieses Rechners lief, zugeteilt war oder geladen wurde. Ob am Läufer zugleich ein Programm am
Leitstand vorbei hängt, steht daneben (`Knoten.laeufer_umgehungen`); das deutet die Regel.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .modelle import Dienst, Knoten, Prozesslast, Rechnerlast, Verbund
from .text import komma
from .werte import Auftragszustand, Hintergrundstufe, Laeuferrolle, Modellzustand

#: Art der Dienste, die ein Modell-Läufer sind (Adapterart im Verzeichnis)
ART_LAEUFER = "openai_kompatibel"
#: Reihenfolge der Stufen des Hintergrunds: der Abstand gilt für den Rückweg von einer Stufe, die schon gilt
STUFENRANG = {Hintergrundstufe.FREI: 0, Hintergrundstufe.GEDROSSELT: 1, Hintergrundstufe.ANGEHALTEN: 2}


def laeuferdienste(verbund: Verbund, knoten: str) -> list[Dienst]:
    """Die Modell-Läufer des Rechners: Dienste auf ihm, die ein Läufer sind (nicht extern, nicht sein Maschinenraum)."""
    return [d for d in verbund.dienste_auf(knoten) if d.art == ART_LAEUFER and not d.extern]


@dataclass
class Laeuferarbeit:
    """Was die Leitstelle gerade auf den Läufern eines Rechners tut."""

    auftraege: int                    # laufen dort oder sind dort zugeteilt
    laedt: bool                       # lädt dort gerade ein Modell oder eine Instanz
    zuletzt_s: float | None           # letzte Nutzung eines Modells dort (Beginn oder Ende eines Auftrags, Laden)


def laeuferarbeit(verbund: Verbund, knoten: str) -> Laeuferarbeit:
    dienste = {d.kennung for d in laeuferdienste(verbund, knoten)}
    modelle = [m for m in verbund.modelle.values() if m.dienst in dienste]
    auftraege = sum(1 for a in verbund.auftraege.values()
                    if a.dienst in dienste and a.zustand in (Auftragszustand.LAEUFT, Auftragszustand.ZUGETEILT))
    zuletzt = max((m.letzte_nutzung_s for m in modelle if m.letzte_nutzung_s is not None), default=None)
    return Laeuferarbeit(auftraege=auftraege, laedt=any(m.zustand == Modellzustand.LAEDT for m in modelle), zuletzt_s=zuletzt)


def ohne_auftrag_seit(verbund: Verbund, knoten: str, p: Prozesslast) -> float | None:
    """Seit wann der Arbeiter über der Schwelle rechnet, ohne dass die Leitstelle auf dem Läufer arbeitet: das Spätere
    von Beginn der Reihe über der Schwelle und letzter Nutzung. None, wenn er kein Arbeiter ist, gerade darunter liegt
    oder die Leitstelle dort gerade arbeitet."""
    if p.rolle != Laeuferrolle.ARBEITER or p.ueber_seit_s is None:
        return None
    ueber = p.ueber_seit_s
    arbeit = laeuferarbeit(verbund, knoten)
    if arbeit.auftraege or arbeit.laedt:
        return None
    return max(ueber, arbeit.zuletzt_s) if arbeit.zuletzt_s is not None else ueber


def arbeitet_ohne_auftrag(verbund: Verbund, knoten: str, p: Prozesslast) -> bool:
    """Befund: rechnet seit mindestens der Frist ohne Auftrag (siehe oben)."""
    seit = ohne_auftrag_seit(verbund, knoten, p)
    return seit is not None and verbund.zeit_s - seit >= verbund.regelwerk.laeufer_frist_s


def ohne_auftrag(verbund: Verbund, k: Knoten) -> list[Prozesslast]:
    """Die Arbeiter des Läufers eines Rechners, die gerade ohne Auftrag rechnen (nur mit gemessener Liste)."""
    if k.last is None or not k.last.gemessen:
        return []
    return [p for p in k.last.prozesse if arbeitet_ohne_auftrag(verbund, k.kennung, p)]


def last_uebernehmen(verbund: Verbund, knoten: str, gemessen: bool, kerne_zahl: int, prozesse: list[Prozesslast], fremd_prozent: float | None) -> None:
    """Eine Meldung knoten.last in den Verbund: je Prozess die Reihe über der Schwelle fortschreiben (dieselbe pid mit
    derselben Modelldatei setzt sie fort, sonst beginnt sie neu), Vermerk "wird beendet" behalten, Fremdlast im Fenster
    der Frist halten. `prozesse` tragen die neue Messung (cpu_prozent), Reihe und Vermerk kommen von hier."""
    k = verbund.knoten[knoten]
    r, jetzt = verbund.regelwerk, verbund.zeit_s
    alt = {(p.pid, p.modelldatei): p for p in k.last.prozesse} if k.last else {}
    neu = []
    for p in prozesse:
        vorher = alt.get((p.pid, p.modelldatei))
        ueber = p.cpu_prozent is not None and p.cpu_prozent >= r.laeufer_schwelle_prozent
        seit = (vorher.ueber_seit_s if vorher and vorher.ueber_seit_s is not None else jetzt) if ueber else None
        neu.append(p.model_copy(update={"ueber_seit_s": seit, "beenden_s": vorher.beenden_s if vorher else None}))
    fremd = [(t, w) for t, w in (k.last.fremd if k.last else []) if jetzt - t < r.last_frist_s]
    if fremd_prozent is not None:
        fremd.append((jetzt, fremd_prozent))
    k.last = Rechnerlast(zeit_s=jetzt, gemessen=gemessen, kerne=kerne_zahl, prozesse=neu, fremd=fremd)


def fremd_mittel(verbund: Verbund, k: Knoten) -> float | None:
    """Fremdlast des Rechners im gleitenden Mittel über `last_frist_s`; None ohne Messung darin."""
    return k.last.fremd_mittel(verbund.zeit_s, verbund.regelwerk.last_frist_s) if k.last else None


# ── Sätze ────────────────────────────────────────────────────────────────
def prozent(x: float) -> str:
    return f"{komma(x, 0)} %"


def kerne(cpu_prozent: float | None) -> str:
    """Prozent eines Kerns als Kerne mit Komma: 98 -> '1,0'."""
    return komma((cpu_prozent or 0.0) / 100, 1)


def dauer(s: float) -> str:
    return f"{komma(s / 3600, 1)} h" if s >= 3600 else f"{max(1, round(s / 60))} min"


def datei(modelldatei: str) -> str:
    """Name der Modelldatei ohne Ordner (der volle Pfad steht im Lagebild)."""
    return PurePosixPath(modelldatei).name if modelldatei else "ohne Modelldatei"


def befund(verbund: Verbund, k: Knoten, p: Prozesslast) -> str:
    """Satz für den Verlauf, wenn ein Arbeiter ohne Auftrag erkannt ist."""
    seit = ohne_auftrag_seit(verbund, k.kennung, p)
    satz = (f"Läufer auf {k.name}: {p.name} (Prozess {p.pid}, {datei(p.modelldatei)}) rechnet seit "
            f"{dauer(verbund.zeit_s - (verbund.zeit_s if seit is None else seit))} ohne Auftrag der Leitstelle mit {kerne(p.cpu_prozent)} Kernen")
    return f"{satz}; am Läufer hängt {', '.join(k.laeufer_umgehungen)}" if k.laeufer_umgehungen else satz
