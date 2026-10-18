"""Steckbrief je Modell zusammensetzen (PROTOKOLL 4.8): von Hand Eingetragenes geht vor, dann die Auskunft des Dienstes,
dann Abgeleitetes; Messwerte aus den jüngsten fertigen Aufträgen. Reine Funktionen, der Betrieb liefert die Quellen."""

from __future__ import annotations

import statistics
from collections import defaultdict

from ..kern.modelle import Modell
from ..kern.werte import Eignung, Zone
from ..ports.ablage.eintraege import AuftragEintrag, SteckbriefEintrag
from ..protokoll.knoten import Selbstauskunft
from ..protokoll.steckbrief import Messwerte, Quelle, Steckbrief

LANGE_TEXTE_AB = 100_000              # Token Kontext, ab denen ein Modell für lange Texte taugt
MESSUNG_JE_FAMILIE = 100              # jüngste fertige Aufträge je Modellfamilie
TEMPO_AB_S = 0.2                      # kürzere Erzeugungszeiten taugen nicht für Token je Sekunde
STROM_ANTEIL = 0.9                    # kam das erste Stück früher als bei diesem Anteil der Rechenzeit, war es ein Strom


def _median(werte: list[float]) -> float | None:
    return round(statistics.median(werte), 2) if werte else None


def messwerte_aus(auftraege: list[AuftragEintrag]) -> dict[str, Messwerte]:
    """Je Modellfamilie aus den jüngsten fertigen Aufträgen (die Liste kommt neueste zuerst)."""
    je_familie: dict[str, list[AuftragEintrag]] = defaultdict(list)
    for a in auftraege:
        if a.familie and len(je_familie[a.familie]) < MESSUNG_JE_FAMILIE:
            je_familie[a.familie].append(a)
    aus = {}
    for familie, xs in je_familie.items():
        dauer = [a.ende_s - a.start_s for a in xs if a.ende_s is not None and a.start_s is not None]
        tempo = []
        for a in xs:
            if a.token_aus and a.ende_s is not None and a.start_s is not None:
                dauer_a = a.ende_s - a.start_s
                # Mit Strom zählt die Zeit nach dem ersten Stück; ohne Strom kommt alles am Ende (erstes Stück so lang wie
                # die Rechenzeit), dann gilt die ganze Rechenzeit
                erst = a.erstes_stueck_s if a.erstes_stueck_s is not None and a.erstes_stueck_s < STROM_ANTEIL * dauer_a else 0.0
                erzeugen = dauer_a - erst
                if erzeugen > TEMPO_AB_S:
                    tempo.append(a.token_aus / erzeugen)
        aus[familie] = Messwerte(auftraege=len(xs), rechenzeit_s=_median(dauer), token_je_s=_median(tempo),
                                 erstes_stueck_s=_median([a.erstes_stueck_s for a in xs if a.erstes_stueck_s is not None]))
    return aus


def zusammensetzen(m: Modell, auskunft: Selbstauskunft, hand: SteckbriefEintrag | None, kontext: int | None, zone: Zone,
                   anfragen_je_minute: int | None, gemessen: Messwerte) -> Steckbrief:
    herkunft: dict[str, Quelle] = {}

    def waehlen(feld: str, von_hand, vom_dienst):
        if von_hand:
            herkunft[feld] = Quelle.HAND
            return von_hand
        if vom_dienst:
            herkunft[feld] = Quelle.DIENST
            return vom_dienst
        return None

    zweck = waehlen("zweck", hand.zweck.strip() if hand else "", auskunft.zweck) or ""
    eignung = list(waehlen("eignung", hand.eignung if hand else [], auskunft.eignung) or [])
    sprachen = list(waehlen("sprachen", hand.sprachen if hand else [], auskunft.sprachen) or [])
    if kontext and kontext >= LANGE_TEXTE_AB and Eignung.LANGE_TEXTE not in eignung and herkunft.get("eignung") != Quelle.HAND:
        eignung.append(Eignung.LANGE_TEXTE)
        herkunft.setdefault("eignung", Quelle.ABGELEITET)
    for feld, wert in (("kontext", kontext), ("parameter_mrd", m.parameter_mrd if m.parameter_mrd else None), ("quantisierung", auskunft.quantisierung)):
        if wert is not None:
            herkunft[feld] = Quelle.DIENST
    if gemessen.auftraege or gemessen.ladezeit_s is not None:
        herkunft["gemessen"] = Quelle.GEMESSEN
    return Steckbrief(zweck=zweck, eignung=eignung, sprachen=sprachen, faehigkeiten=sorted(m.faehigkeiten, key=lambda f: f.value), kontext=kontext,
                      parameter_mrd=m.parameter_mrd or None, quantisierung=auskunft.quantisierung, zone=zone,
                      anfragen_je_minute=anfragen_je_minute, gemessen=gemessen, herkunft=herkunft)
