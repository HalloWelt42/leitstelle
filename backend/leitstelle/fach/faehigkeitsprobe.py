"""Fähigkeitsprobe: was ein externer Anbieter über seine Modelle nicht sagt, belegt eine kleine Aufgabe je Modell.

Hetzner nennt in `/v1/models` nur Namen und Kontext; ob ein Modell Bilder annimmt, steht nirgends (die Modelle sind laut
Seiten Dritter multimodal, der Anbieter belegt es nicht). Die Probe schickt je Modell ein kleines Bild (eine rote Fläche)
mit einer Frage; nennt die Antwort die Farbe, ist "Bild beschreiben" belegt, lehnt der Anbieter das Bild ab oder antwortet
etwas anderes, ist es nicht belegt. Das Ergebnis steht mit Zeitpunkt im Steckbrief (Quelle gemessen) und ändert die
Fähigkeiten des Modells, bis zur nächsten Probe. Jede Probe ist eine Anfrage und zählt gegen die Grenzen des Anbieters;
darum nur von Hand ("Fähigkeiten prüfen" am Dienst), nie im Takt, und nur, wenn die Grenzen sie gerade zulassen.
Überlast, Zeitüberschreitung und Abriss sagen nichts über die Fähigkeit: dann bleibt das bisherige Ergebnis stehen.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import struct
import zlib
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from ..kern.fenster import Bedarf
from ..kern.modelle import Modell
from ..kern.text import aufzaehlung
from ..kern.werte import WORT, Faehigkeit
from ..ports.ablage.eintraege import DienstEintrag, FaehigkeitsprobeEintrag, PruefEintrag
from ..ports.dienste import DienstFehler
from .betrieb import Betrieb
from .fehler import Ablehnung
from .vermittlung import token_schaetzen, warte_s_aus

ANTWORT_TOKEN = 400                  # Platz für die Antwort; denkende Modelle brauchen etwas davon zum Denken
MELDUNG_ZEICHEN = 160


def _png(farbe: tuple[int, int, int], kante: int = 64) -> bytes:
    """Ein einfarbiges Bild als PNG, ohne Bildbibliothek."""
    def block(art: bytes, daten: bytes) -> bytes:
        return struct.pack(">I", len(daten)) + art + daten + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF)
    zeilen = (b"\x00" + bytes(farbe) * kante) * kante
    return (b"\x89PNG\r\n\x1a\n" + block(b"IHDR", struct.pack(">IIBBBBB", kante, kante, 8, 2, 0, 0, 0)) + block(b"IDAT", zlib.compress(zeilen))
            + block(b"IEND", b""))


@dataclass(frozen=True)
class Probe:
    """Eine Aufgabe, die eine Fähigkeit belegt: die Antwort enthält eines der erwarteten Wörter."""

    faehigkeit: Faehigkeit
    nachrichten: list[dict[str, Any]]
    erwartet: tuple[str, ...]


ROTES_BILD = "data:image/png;base64," + base64.b64encode(_png((220, 20, 20))).decode("ascii")
PROBEN = [Probe(Faehigkeit.BILD_BESCHREIBEN,
                [{"role": "user", "content": [{"type": "text", "text": "Welche Farbe hat dieses Bild? Antworte mit einem Wort."},
                                              {"type": "image_url", "image_url": {"url": ROTES_BILD}}]}],
                ("rot", "red"))]


class Probenausgang(str, Enum):
    BELEGT = "belegt"                # die Antwort zeigt die Fähigkeit
    NICHT_BELEGT = "nicht_belegt"    # abgelehnt oder falsch beantwortet
    UNKLAR = "unklar"                # Überlast, keine Antwort, Abriss: sagt nichts, das bisherige Ergebnis bleibt


AUSGANG_WORT = {Probenausgang.BELEGT: "belegt", Probenausgang.NICHT_BELEGT: "nicht belegt", Probenausgang.UNKLAR: "unklar"}


class Probenergebnis(BaseModel):
    familie: str
    name: str
    faehigkeit: Faehigkeit
    ausgang: Probenausgang
    meldung: str


def _kurz(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MELDUNG_ZEICHEN else text[:MELDUNG_ZEICHEN - 3] + "..."


def _antworttext(roh: bytes) -> str:
    """Inhalt und Denken einer Antwort im OpenAI-Format (ein denkendes Modell nennt die Farbe vielleicht nur im Denken)."""
    try:
        daten = json.loads(roh)
    except ValueError:
        return roh.decode("utf-8", "replace")
    wahlen = daten.get("choices") if isinstance(daten, dict) else None
    nachricht = wahlen[0].get("message") if wahlen and isinstance(wahlen[0], dict) else None
    if not isinstance(nachricht, dict):
        return ""
    return " ".join(str(nachricht.get(f) or "") for f in ("content", "reasoning_content", "reasoning")).strip()


def _fehlertext(roh: bytes) -> str:
    try:
        fehler = json.loads(roh).get("error")
    except (ValueError, AttributeError):
        return roh.decode("utf-8", "replace")
    return str(fehler.get("message", fehler)) if isinstance(fehler, dict) else str(fehler)


async def _probieren(b: Betrieb, e: DienstEintrag, m: Modell, probe: Probe) -> Probenergebnis:
    """Eine Probe an einem Modell; Token werden gebucht wie bei jeder Anfrage."""
    koerper = {"model": b.ort(m.kennung).anfragename, "messages": probe.nachrichten, "max_tokens": ANTWORT_TOKEN, "stream": False}

    def ergebnis(ausgang: Probenausgang, meldung: str) -> Probenergebnis:
        return Probenergebnis(familie=m.familie, name=m.name, faehigkeit=probe.faehigkeit, ausgang=ausgang, meldung=_kurz(meldung))

    adapter, buchung, frist = b.adapter[e.kennung], f"probe:{uuid4().hex}", b.konfig.faehigkeitsprobe_s
    ein, aus = token_schaetzen(koerper)
    b.verbund.token_vorbuchen(e.kennung, buchung, m.familie, ein, aus, b.uhr.jetzt())
    try:
        antwort = await asyncio.wait_for(adapter.anfrage("/v1/chat/completions", koerper), frist)
        try:
            roh = await asyncio.wait_for(antwort.lesen(), frist)
        finally:
            await antwort.schliessen()
    except TimeoutError:
        b.verbund.token_abschliessen(e.kennung, buchung, b.uhr.jetzt())
        return ergebnis(Probenausgang.UNKLAR, f"keine Antwort in {frist:.0f} s")
    except DienstFehler as f:
        b.verbund.token_abschliessen(e.kennung, buchung, b.uhr.jetzt())
        return ergebnis(Probenausgang.UNKLAR, f.meldung)
    if antwort.status in adapter.ueberlast_status:
        b.dienst_ueberlastet(e.kennung, warte_s_aus(antwort.kopf), antwort.status)
        b.verbund.token_streichen(e.kennung, buchung)
        return ergebnis(Probenausgang.UNKLAR, f"Anbieter ausgelastet (Antwort {antwort.status})")
    vb = antwort.verbrauch
    b.verbund.token_abschliessen(e.kennung, buchung, b.uhr.jetzt(), vb.token_ein if vb else None, vb.token_aus if vb else None)
    if antwort.status >= 400:
        return ergebnis(Probenausgang.NICHT_BELEGT, f"abgelehnt (Antwort {antwort.status}): {_fehlertext(roh)}")
    text = _antworttext(roh)
    belegt = any(re.search(rf"\b{w}\b", text, re.IGNORECASE) for w in probe.erwartet)
    return ergebnis(Probenausgang.BELEGT if belegt else Probenausgang.NICHT_BELEGT, f"antwortete: {text or '(leer)'}")


def _bedarf(p: Probe) -> Bedarf:
    ein, aus = token_schaetzen({"messages": p.nachrichten, "max_tokens": ANTWORT_TOKEN})
    return Bedarf(anfragen=1, token_ein=ein, token_aus=aus)


async def pruefen(b: Betrieb, dienst: str, wer: str) -> list[Probenergebnis]:
    """Je Modell des Dienstes (ohne Einbettung, je Familie einmal) jede Probe; Ergebnisse speichern und übernehmen."""
    e = b.dienste.get(dienst)
    if e is None:
        raise Ablehnung("unbekannt", "Diesen Dienst gibt es nicht.")
    if not e.extern:
        raise Ablehnung("nicht_pruefbar", "Fähigkeiten prüft die Leitstelle nur bei externen Anbietern; Modell-Läufer und Maschinenraum melden sie selbst.")
    if not b.verbund.dienste[dienst].nutzbar:
        raise Ablehnung("dienst_nicht_erreichbar", f"{e.name} ist gerade nicht bereit; prüfen geht, sobald er antwortet.")
    modelle = sorted({m.familie: m for m in b.verbund.modelle_von(dienst) if not m.zusatz and Faehigkeit.EINBETTUNG not in m.faehigkeiten}.values(),
                     key=lambda m: m.name.lower())
    if not modelle:
        raise Ablehnung("kein_modell", f"{e.name} meldet kein Modell, das sich prüfen ließe.")
    je_modell = sum((_bedarf(p) for p in PROBEN), Bedarf())
    frei = b.frei(dienst, sum((je_modell for _ in modelle), Bedarf()))
    if frei.in_s > 0:
        raise Ablehnung("grenze", f"{e.name}: {frei.grund}; in etwa {frei.in_s:.0f} s erneut prüfen. Je Modell kostet die Probe eine Anfrage.")
    ergebnisse = [await _probieren(b, e, m, p) for m in modelle for p in PROBEN]
    jetzt = b.uhr.jetzt()
    for r in ergebnisse:
        if r.ausgang != Probenausgang.UNKLAR:
            eintrag = FaehigkeitsprobeEintrag(familie=r.familie, faehigkeit=r.faehigkeit, belegt=r.ausgang == Probenausgang.BELEGT, zeit_s=jetzt,
                                              meldung=r.meldung)
            await b.ablage.proben.speichern(eintrag)
            b.probe_uebernehmen(eintrag)
    satz = aufzaehlung([f"{r.name} {WORT[r.faehigkeit.value]} {AUSGANG_WORT[r.ausgang]}" for r in ergebnisse])
    await b.ablage.pruefung.anhaengen(PruefEintrag(zeit_s=jetzt, wer=wer, was=f"Fähigkeiten geprüft: {satz}", gegenstand=e.name))
    b.melden(f"{e.name}: Fähigkeiten geprüft, {satz}")
    return ergebnisse

