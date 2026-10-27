"""Steckbrief je Modell zusammensetzen (PROTOKOLL 4.8): von Hand Eingetragenes geht vor, dann die Auskunft des Dienstes,
dann Abgeleitetes; Messwerte aus den jüngsten fertigen Aufträgen. Reine Funktionen, der Betrieb liefert die Quellen."""

from __future__ import annotations

import re
import statistics
from collections import defaultdict

from pydantic import BaseModel

from ..kern.modelle import Modell
from ..kern.werte import Eignung, Faehigkeit, Zone
from ..ports.ablage.eintraege import AuftragEintrag, FaehigkeitsprobeEintrag, SteckbriefEintrag
from ..protokoll.knoten import Selbstauskunft
from ..protokoll.steckbrief import Bildsteckbrief, Faehigkeitsprobe, Messwerte, Quelle, Steckbrief

LANGE_TEXTE_AB = 100_000              # Token Kontext, ab denen ein Modell für lange Texte taugt
MESSUNG_JE_FAMILIE = 100              # jüngste fertige Aufträge je Modellfamilie
TEMPO_AB_S = 0.2                      # kürzere Erzeugungszeiten taugen nicht für Token je Sekunde
STROM_ANTEIL = 0.9                    # kam das erste Stück früher als bei diesem Anteil der Rechenzeit, war es ein Strom


class Grenzen(BaseModel):
    """Grenzen des Anbieters je Minute, wie der Dienst eingetragen ist."""

    anfragen_je_minute: int | None = None
    token_ein_je_minute: int | None = None
    token_aus_je_minute: int | None = None


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


AKTIV_IM_NAMEN = re.compile(r"(?<![a-z0-9])a(\d+(?:\.\d+)?)b(?![a-z])", re.IGNORECASE)

#: Rolle im Vergleich der Textmodelle eines Dienstes, der Mischmodelle und dichte anbietet (etwa Hetzner: Qwen3.6-35B-A3B
#: und Qwen3.8-27B); die Wahl bleibt bei der App
ROLLE_ZWECK = {Eignung.SCHNELL: "Schnell: wenige Parameter je Schritt aktiv; für kurze Aufgaben",
               Eignung.GRUENDLICH: "Gründlich: alle Parameter je Schritt aktiv; für lange Texte und schwierige Fragen"}


def aktive_im_namen(*namen: str) -> float | None:
    """'Qwen/Qwen3.6-35B-A3B' -> 3, 'gemma-4-26b-a4b-qat' -> 4; None, wenn der Name es nicht sagt."""
    for n in namen:
        if t := AKTIV_IM_NAMEN.search(n or ""):
            return float(t.group(1))
    return None


def aktive_parameter(m: Modell, hand: SteckbriefEintrag | None) -> tuple[float | None, Quelle | None]:
    """Je Schritt aktive Parameter in Milliarden: von Hand, sonst aus dem Namen (A3B: 3), sonst gleich gesamt (ein dichtes
    Modell); ohne bekannte Gesamtzahl unbekannt."""
    if hand is not None and hand.parameter_aktiv_mrd:
        return hand.parameter_aktiv_mrd, Quelle.HAND
    if not m.parameter_mrd:
        return None, None
    im_namen = aktive_im_namen(m.familie, m.name)
    return (im_namen if im_namen is not None and im_namen < m.parameter_mrd else m.parameter_mrd), Quelle.ABGELEITET


def rollen(modelle: list[tuple[Modell, float | None]]) -> dict[str, Eignung]:
    """Schnell und gründlich im Vergleich der Textmodelle eines externen Anbieters (Modell und aktive Parameter): bietet er
    beide Bauarten an (Mischmodell mit wenigen aktiven Parametern und dichtes Modell), heißt das Mischmodell schnell und das
    dichte gründlich. Je Modellkennung; leer, wenn es nichts zu vergleichen gibt (eine Bauart allein sagt nichts über
    schnell oder gründlich)."""
    text = [(m, aktiv) for m, aktiv in modelle if Faehigkeit.TEXT in m.faehigkeiten and m.parameter_mrd and aktiv]
    misch = [m for m, aktiv in text if aktiv < m.parameter_mrd]
    dicht = [m for m, aktiv in text if aktiv >= m.parameter_mrd]
    if not misch or not dicht:
        return {}
    return {m.kennung: Eignung.SCHNELL for m in misch} | {m.kennung: Eignung.GRUENDLICH for m in dicht}


def zusammensetzen(m: Modell, auskunft: Selbstauskunft, hand: SteckbriefEintrag | None, kontext: int | None, zone: Zone, grenzen: Grenzen,
                   gemessen: Messwerte, rolle: Eignung | None = None, proben: list[FaehigkeitsprobeEintrag] | None = None,
                   bild: Bildsteckbrief | None = None) -> Steckbrief:
    """`bild`: was ein Bilddienst über sein Modell sagt; daraus kommen auch Parameter und Quantisierung, wenn der Bericht des
    Dienstes sie nicht nennt (der Maschinenraum kennt sie nicht)."""
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
    if not zweck and rolle is not None:
        zweck, herkunft["zweck"] = ROLLE_ZWECK[rolle], Quelle.ABGELEITET
    eignung = list(waehlen("eignung", hand.eignung if hand else [], auskunft.eignung) or [])
    if herkunft.get("eignung") != Quelle.HAND:
        abgeleitet = ([Eignung.LANGE_TEXTE] if kontext and kontext >= LANGE_TEXTE_AB else []) + ([rolle] if rolle is not None else [])
        for e in abgeleitet:
            if e not in eignung:
                eignung.append(e)
                herkunft.setdefault("eignung", Quelle.ABGELEITET)
    sprachen = list(waehlen("sprachen", hand.sprachen if hand else [], auskunft.sprachen) or [])
    parameter = m.parameter_mrd or (bild.parameter_mrd if bild else None) or None
    quantisierung = auskunft.quantisierung or (bild.quantisierung if bild else None)
    for feld, wert in (("kontext", kontext), ("parameter_mrd", parameter), ("quantisierung", quantisierung), ("bild", bild)):
        if wert is not None:
            herkunft[feld] = Quelle.DIENST
    aktiv, quelle = aktive_parameter(m, hand)
    if quelle is not None:
        herkunft["parameter_aktiv_mrd"] = quelle
    geprueft = [Faehigkeitsprobe(faehigkeit=p.faehigkeit, belegt=p.belegt, zeit_s=p.zeit_s, meldung=p.meldung) for p in proben or []]
    if geprueft:
        herkunft["geprueft"] = Quelle.GEMESSEN
    if gemessen.auftraege or gemessen.ladezeit_s is not None:
        herkunft["gemessen"] = Quelle.GEMESSEN
    return Steckbrief(zweck=zweck, eignung=eignung, sprachen=sprachen, faehigkeiten=sorted(m.faehigkeiten, key=lambda f: f.value), kontext=kontext,
                      parameter_mrd=parameter, parameter_aktiv_mrd=aktiv, quantisierung=quantisierung, zone=zone,
                      anfragen_je_minute=grenzen.anfragen_je_minute, token_ein_je_minute=grenzen.token_ein_je_minute,
                      token_aus_je_minute=grenzen.token_aus_je_minute, geprueft=geprueft, bild=bild, gemessen=gemessen, herkunft=herkunft)
