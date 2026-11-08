"""Einordnen (LS-26, PROTOKOLL 6.7): ein Text und Fragen mit festen Möglichkeiten. Das Modell schreibt keine Antwort;
es nennt nur einen Buchstaben (oder ja, nein), und die Leitstelle liest die Wahrscheinlichkeiten aller Möglichkeiten aus
dem ersten Token. Das ist schneller als eine Antwort in JSON und liefert nie eine ungültige Form.

Gemessen am 80B über die Leitstelle (08.11.2026): 0,2 s je Frage statt 1,75 s für dieselbe Frage als JSON-Antwort. Der
Läufer nennt höchstens 10 Alternativen je Token (mehr lehnt er ab), darum höchstens 10 Möglichkeiten je Aufruf; mehr
rechnet die Leitstelle in Runden (je Gruppe die stärkste, dann die Sieger gegeneinander). Mit `max_tokens` 1 antwortet
der Läufer leer, darum 2. Die Werte sind nicht geeicht: bei einem mehrdeutigen Fall nannte das 80B 100 %.

Jeder Aufruf des Modells ist ein eigener Auftrag der Fähigkeit `einordnen` (Rechte, Rang, Einzel oder Masse wie immer);
wie er ausgeführt wird, entscheidet der Aufrufer (`Rechnen`). Text und Anweisung stehen vorn und sind für alle Fragen
gleich, damit der Läufer den Anfang aus seinem Zwischenspeicher nimmt.
"""

from __future__ import annotations

import json
import math
from collections.abc import Awaitable, Callable
from typing import Any

from ..protokoll.fassade import Einordnungsanfrage, Einordnungsantwort, Frage, Fragart
from .fehler import Ablehnung

BUCHSTABEN = "ABCDEFGHIJ"
JE_AUFRUF = len(BUCHSTABEN)          # höchstens so viele Alternativen nennt der Läufer je Token
ANTWORT_TOKEN = 2                    # mit 1 antwortet der Läufer leer (gemessen 08.11.2026)
JA, NEIN = "ja", "nein"
JA_WOERTER = ("ja", "yes")             # erkannt auch am Anfang: das erste Token ist oft nur ein Teil des Worts
NEIN_WOERTER = ("nein", "no", "nee", "nej")   # "nein" ist beim 80B "ne" + "in" (gemessen 08.11.2026)
MINDEST_ANTEIL = 0.5                 # so viel der Wahrscheinlichkeit muss auf passende Antworten fallen, sonst keine Wahl
STELLEN = 4                          # Nachkommastellen der Wahrscheinlichkeiten
SYSTEM = ("Du ordnest einen Text ein. Antworte nur mit dem Buchstaben der passenden Möglichkeit oder mit ja oder nein, "
          "wie die Frage es verlangt, ohne weiteren Text.")

#: Ein Aufruf des Modells: Körper im OpenAI-Format (ohne `model`) hinein, Antwortkörper heraus
Rechnen = Callable[[dict[str, Any]], Awaitable[bytes]]


class _Zaehler:
    def __init__(self, rechnen: Rechnen) -> None:
        self.rechnen, self.anzahl = rechnen, 0

    async def __call__(self, koerper: dict[str, Any]) -> bytes:
        self.anzahl += 1
        return await self.rechnen(koerper)


def koerper(anfrage: Einordnungsanfrage, frage: str) -> dict[str, Any]:
    """Ein Aufruf: gleicher Anfang für alle Fragen (System, Anweisung, Text), dann die Frage."""
    system = SYSTEM + (f"\n\n{anfrage.anweisung.strip()}" if anfrage.anweisung and anfrage.anweisung.strip() else "")
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": f"Text:\n{anfrage.text}\n\n{frage}"}],
            "max_tokens": ANTWORT_TOKEN, "temperature": 0, "logprobs": True, "top_logprobs": JE_AUFRUF, "stream": False}


def kandidaten(roh: bytes) -> tuple[str, list[tuple[str, float]]]:
    """Antworttext und die Kandidaten des ersten Tokens mit ihrer Wahrscheinlichkeit."""
    try:
        wahl = json.loads(roh)["choices"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        raise Ablehnung("dienst_fehler", "Die Antwort des Modells hat nicht die erwartete Form.") from None
    inhalt = str((wahl.get("message") or {}).get("content") or "")
    tokens = (wahl.get("logprobs") or {}).get("content") or []
    if not tokens:
        raise Ablehnung("dienst_fehler", "Das Modell liefert keine Wahrscheinlichkeiten; Einordnen braucht ein Modell auf einem Modell-Läufer.")
    erstes = tokens[0]
    return inhalt, [(str(k.get("token", "")), math.exp(float(k.get("logprob", -math.inf)))) for k in (erstes.get("top_logprobs") or [erstes])]


def _wort(token: str) -> str:
    return token.strip().strip(":.)\"'").lower()


def _anfang(wort: str, woerter: tuple[str, ...]) -> bool:
    return bool(wort) and any(w.startswith(wort) for w in woerter)


def _verteilt(werte: dict[str, float], inhalt: str) -> dict[str, float]:
    """Nur, wenn das Modell überwiegend mit einer der Möglichkeiten antwortete; ein winziger Rest würde sonst auf 100 %
    hochgerechnet (gesehen 08.11.2026: "ne" für nein nicht erkannt, ein Rest von ja wurde zu 1)."""
    summe = sum(werte.values())
    if summe < MINDEST_ANTEIL:
        raise Ablehnung("dienst_fehler", f"Das Modell antwortete mit keiner der Möglichkeiten ({inhalt[:40]!r}).")
    return {k: v / summe for k, v in werte.items()}


def buchstaben_lesen(roh: bytes, schluessel: list[str]) -> dict[str, float]:
    """Wahrscheinlichkeit je Möglichkeit (Buchstabe A, B, ... in dieser Reihenfolge), zusammen 1."""
    inhalt, paare = kandidaten(roh)
    werte = dict.fromkeys(schluessel, 0.0)
    for token, p in paare:
        w = _wort(token).upper()
        if len(w) == 1 and w in BUCHSTABEN[:len(schluessel)]:
            werte[schluessel[BUCHSTABEN.index(w)]] += p
    return _verteilt(werte, inhalt)


def ja_lesen(roh: bytes) -> float:
    """Wahrscheinlichkeit für ja (ja, Ja, yes und Varianten zusammen) gegen nein."""
    inhalt, paare = kandidaten(roh)
    werte = {JA: 0.0, NEIN: 0.0}
    for token, p in paare:
        w = _wort(token)
        if _anfang(w, JA_WOERTER):
            werte[JA] += p
        elif _anfang(w, NEIN_WOERTER):
            werte[NEIN] += p
    return _verteilt(werte, inhalt)[JA]


def gruppen(schluessel: list[str]) -> list[list[str]]:
    """Gleich große Gruppen zu höchstens JE_AUFRUF (11 Möglichkeiten: 6 und 5, nicht 10 und 1)."""
    anzahl = math.ceil(len(schluessel) / JE_AUFRUF)
    groesse = math.ceil(len(schluessel) / anzahl)
    return [schluessel[i:i + groesse] for i in range(0, len(schluessel), groesse)]


def _gerundet(werte: dict[str, float]) -> dict[str, float]:
    return {k: round(v, STELLEN) for k, v in werte.items()}


async def _auswahl(rechnen: Rechnen, anfrage: Einordnungsanfrage, frage: Frage) -> Einordnungsantwort:
    stufe = frage.art == Fragart.STUFE
    kopf = f"Frage: {frage.frage}" + ("\nDie Stufen stehen in aufsteigender Reihenfolge." if stufe else "")
    schluessel, runden = list(frage.moeglichkeiten), 0
    while True:
        runden += 1
        ergebnisse = []
        for g in gruppen(schluessel):
            liste = "\n".join(f"{BUCHSTABEN[i]}: {frage.moeglichkeiten[k]}" for i, k in enumerate(g))
            ergebnisse.append(buchstaben_lesen(await rechnen(koerper(anfrage, f"{kopf}\n{liste}\nAntworte mit einem Buchstaben.")), g))
        if len(ergebnisse) == 1:
            werte = ergebnisse[0]
            break
        schluessel = [max(e, key=lambda k, e=e: e[k]) for e in ergebnisse]
    mittel = round(sum(i * werte.get(k, 0.0) for i, k in enumerate(frage.moeglichkeiten)), STELLEN) if stufe else None
    return Einordnungsantwort(wahl=max(werte, key=lambda k: werte[k]), wahrscheinlichkeiten=_gerundet(werte), mittel=mittel, runden=runden)


async def _ja_nein(rechnen: Rechnen, anfrage: Einordnungsanfrage, frage: Frage) -> Einordnungsantwort:
    p = ja_lesen(await rechnen(koerper(anfrage, f"Frage: {frage.frage}\nAntworte mit ja oder nein.")))
    return Einordnungsantwort(wahl=JA if p >= 0.5 else NEIN, wahrscheinlichkeiten=_gerundet({JA: p, NEIN: 1 - p}))


async def _mehrfach(rechnen: Rechnen, anfrage: Einordnungsanfrage, frage: Frage) -> Einordnungsantwort:
    werte = {}
    for k, beschreibung in frage.moeglichkeiten.items():
        werte[k] = ja_lesen(await rechnen(koerper(anfrage, f"Frage: {frage.frage}\nTrifft dies zu: {beschreibung}\nAntworte mit ja oder nein.")))
    return Einordnungsantwort(wahl=[k for k, p in werte.items() if p >= 0.5], wahrscheinlichkeiten=_gerundet(werte))


ABLAUF = {Fragart.AUSWAHL: _auswahl, Fragart.STUFE: _auswahl, Fragart.JA_NEIN: _ja_nein, Fragart.MEHRFACH: _mehrfach}


async def einordnen(anfrage: Einordnungsanfrage, rechnen: Rechnen) -> tuple[dict[str, Einordnungsantwort], int]:
    """Alle Fragen der Reihe nach; Ergebnis: Antwort je Frage und wie oft das Modell gerechnet hat."""
    zaehler = _Zaehler(rechnen)
    antworten = {name: await ABLAUF[f.art](zaehler, anfrage, f) for name, f in anfrage.fragen.items()}
    return antworten, zaehler.anzahl
