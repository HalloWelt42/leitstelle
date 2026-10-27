"""Bildablauf für Bilddienste im üblichen Bildformat (die Form von `POST /v1/images/generations` der OpenAI-Schnittstelle).

So sprechen die Dienste des Bildwerks, je Bildmodell ein Prozess im Maschinenraum. Die Anfrage geht über die
Durchleitung an `v1/images/generations` mit Beschreibung, Größe, Anzahl, Startwert und wahlweise Schritten; die Bilder
kommen als `data[].b64_json` (PNG) in der Antwort. `model` schickt der Ablauf nicht mit: der Dienst hält genau ein Modell,
gewählt hat die Leitstelle schon. Was das Modell annimmt, sagt der Dienst unter `GET v1/models` im Feld `steckbrief` des
Modelleintrags (Größen, Schritte, Anzahl, Bearbeiten); fehlt es, gelten die Vorgabegrenzen der Fassade.

Abbruch heißt Verbindung schließen: der Auftrag endet in der Leitstelle, die offene Anfrage wird abgebrochen und ihre
Verbindung geschlossen; der Dienst sieht das und hört beim nächsten Schritt auf. Nichts wird nachgeschickt.

Fehler des Dienstes kommen als `DienstFehler` mit einem Grundwort (PROTOKOLL 7): 400 und 422 `eingabe` (Größe,
Schritte, Form), 409 `anderes_modell`, 501 `nicht_unterstuetzt`, 503 `dienst_nicht_bereit` (Modell lädt oder ist gestört),
499 `abgebrochen` (der Dienst hat die Rechnung abgebrochen, weil seine Verbindung zuging), alles andere `dienst_fehler`.
Eine Absage der Durchleitung selbst (Körper mit `grund` und `meldung`, PROTOKOLL 4.2), etwa weil der Dienst gerade nicht
läuft, heißt `dienst_nicht_erreichbar`.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from ....protokoll.steckbrief import Bildsteckbrief
from ..schnittstelle import DienstFehler, Durchleitung
from .schnittstelle import Bildauftrag, Bildergebnis, Senden

log = logging.getLogger("leitstelle.bilder")

PFAD_ERZEUGEN = "v1/images/generations"
PFAD_MODELLE = "v1/models"

# Grundwort je Antwortcode des Dienstes (PROTOKOLL 7); was hier fehlt, ist ein Fehler des Dienstes
GRUND_JE_STATUS = {400: "eingabe", 422: "eingabe", 409: "anderes_modell", 501: "nicht_unterstuetzt", 503: "dienst_nicht_bereit",
                   499: "abgebrochen"}


class BildformatAblauf(BaseModel):
    """Einstellung des Ablaufs (Umgebung `LEITSTELLE_BILDABLAEUFE` je Dienst, oder `LEITSTELLE_BILDABLAUF_VORGABE` für
    alle Bilddienste ohne eigenen Eintrag). Der Ablauf braucht nichts weiter: was das Modell annimmt, sagt der Dienst."""

    art: Literal["bildformat"] = "bildformat"


class _Bilddaten(BaseModel):
    b64_json: str


class _Bildantwort(BaseModel):
    data: list[_Bilddaten]


class _Modelleintrag(BaseModel):
    id: str
    steckbrief: dict[str, Any] | None = None


class _Modellliste(BaseModel):
    data: list[_Modelleintrag]


def meldung_aus(daten: Any) -> str:
    """Der Wortlaut eines Fehlers in den Formen, die vorkommen: `detail` (Text oder Liste der Prüffehler), `meldung` (Absage
    der Durchleitung), `error.message` (OpenAI-Format), sonst roh."""
    if isinstance(daten, dict):
        detail = daten.get("detail")
        if isinstance(detail, str):
            return detail[:500]
        if isinstance(detail, list):
            return "; ".join(f"{'.'.join(str(x) for x in f.get('loc', []))}: {f.get('msg', '')}" if isinstance(f, dict) else str(f)
                             for f in detail)[:500]
        if isinstance(daten.get("meldung"), str):
            return daten["meldung"][:500]
        fehler = daten.get("error")
        if isinstance(fehler, dict) and fehler.get("message"):
            return str(fehler["message"])[:500]
    return (daten if isinstance(daten, str) else json.dumps(daten, ensure_ascii=False))[:500]


def fehler_aus(status: int, daten: Any) -> DienstFehler:
    """Eine Absage des Dienstes oder der Durchleitung als `DienstFehler` mit Grundwort."""
    text = meldung_aus(daten)
    if isinstance(daten, dict) and "grund" in daten and "meldung" in daten:
        return DienstFehler("dienst_nicht_erreichbar", f"Durchleitung ({status}): {text}", wiederholbar=True)
    return DienstFehler(GRUND_JE_STATUS.get(status, "dienst_fehler"), f"Bilddienst ({status}): {text}")


class Bildformat:
    def __init__(self, einstellung: BildformatAblauf) -> None:
        self.e = einstellung

    async def _anfrage(self, senden: Senden, methode: str, pfad: str, koerper: Any = None) -> tuple[int, Any]:
        """Eine Anfrage über die Durchleitung; die Verbindung wird immer geschlossen, auch beim Abbruch."""
        inhalt = json.dumps(koerper).encode() if koerper is not None else b""
        kopf = {"content-type": "application/json"} if koerper is not None else {}
        strom = await senden(Durchleitung(methode=methode, pfad=pfad, kopf=kopf, inhalt=inhalt))
        try:
            status, roh = strom.status, await strom.lesen()
        finally:
            await strom.schliessen()
        try:
            return status, json.loads(roh) if roh else {}
        except ValueError:
            return status, roh.decode("utf-8", "replace")

    async def erzeugen(self, senden: Senden, auftrag: Bildauftrag) -> Bildergebnis:
        koerper: dict[str, Any] = {"prompt": auftrag.beschreibung, "size": f"{auftrag.breite}x{auftrag.hoehe}", "n": auftrag.anzahl,
                                   "seed": auftrag.seed, "response_format": "b64_json"}
        if auftrag.schritte is not None:
            koerper["steps"] = auftrag.schritte
        status, daten = await self._anfrage(senden, "POST", PFAD_ERZEUGEN, koerper)
        if status >= 400:
            raise fehler_aus(status, daten)
        try:
            bilder = [base64.b64decode(d.b64_json, validate=True) for d in _Bildantwort.model_validate(daten).data]
        except (ValidationError, binascii.Error, ValueError) as fehler:
            raise DienstFehler("dienst_fehler", f"Der Bilddienst hat keine lesbaren Bilder geliefert: {fehler}"[:500]) from None
        if not bilder:
            raise DienstFehler("dienst_fehler", "Der Bilddienst hat ohne Bild geantwortet.")
        return Bildergebnis(bilder=bilder, seed=auftrag.seed, schritte=auftrag.schritte)

    async def steckbrief(self, senden: Senden) -> Bildsteckbrief | None:
        """Der erste Modelleintrag unter `GET v1/models` mit seinem `steckbrief`. Kennt der Dienst den Weg nicht oder nennt
        keinen Steckbrief, sagt er nichts (None); ist der Steckbrief nicht lesbar, steht das im Protokoll."""
        status, daten = await self._anfrage(senden, "GET", PFAD_MODELLE)
        if status >= 400:
            if status == 404:
                return None
            raise fehler_aus(status, daten)
        try:
            liste = _Modellliste.model_validate(daten)
            eintrag = next((e for e in liste.data if e.steckbrief), None)
            if eintrag is None or eintrag.steckbrief is None:
                return None
            s = eintrag.steckbrief
            return Bildsteckbrief.model_validate({**s, "modell": eintrag.id, "name": s.get("name") or eintrag.id, "abgerufen_s": 0.0})
        except ValidationError as fehler:
            log.warning("Steckbrief des Bilddienstes nicht lesbar: %s", fehler)
            return None
