"""Was alle Router teilen: Zugriff auf die Fachobjekte, Heimnetz-Schutz, Fehlerantworten."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..fach.betrieb import Betrieb
from ..fach.ereignisse import Ereignisbus
from ..fach.fehler import Ablehnung, Zusatz, fehler_inhalt
from ..fach.verzeichnis import Verzeichnis
from ..fach.vermittlung import Vermittlung
from ..konfig import Konfig

# HTTP-Status je Grundwort (PROTOKOLL.md Abschnitt 7 und Verwaltung)
STATUS: dict[str, int] = {
    "unbekannter_schluessel": 401, "faehigkeit_nicht_erlaubt": 403, "zone_nicht_erlaubt": 403, "herkunft_nicht_erlaubt": 403,
    "kontingent": 429, "gesperrt": 429, "halt": 503, "wartung": 503, "kein_modell": 404, "kein_dienst": 503,
    "dienst_nicht_erreichbar": 503, "rechner_schlaeft": 503, "modell_passt_nicht": 503, "dienst_fehler": 502, "nutzer": 409, "anwendung": 499,
    "unbekannt": 404, "in_gebrauch": 409, "doppelt": 409, "instanz_weg": 409, "adresse": 422, "knoten_fehlt": 422, "nicht_anhaltbar": 409,
}


def status_fuer(grund: str) -> int:
    return STATUS.get(grund, 400)


def wieder_in_s(k: Konfig, grund: str) -> int:
    """Retry-After: ein schlafender Rechner wacht selten in Sekunden auf, alles andere ist meist gleich wieder da."""
    return round(k.schlaf_wieder_s if grund == "rechner_schlaeft" else k.wieder_s)


def fehler_antwort(request: Request, grund: str, text: str, zusatz: Zusatz | None = None) -> JSONResponse:
    """Fehler im Format der OpenAI-Schnittstelle, mit dem Grundwort als `code`; bei 429 und 503 mit Retry-After."""
    status = status_fuer(grund)
    kopf = {"Retry-After": str(wieder_in_s(konfig(request), grund))} if status in (429, 503) else {}
    return JSONResponse({"error": fehler_inhalt(grund, text, zusatz)}, status_code=status, headers=kopf)


def ablehnung_antwort(request: Request, a: Ablehnung) -> JSONResponse:
    return fehler_antwort(request, a.grund, a.begruendung, a.zusatz)


def ablehnung_als_fehler(a: Ablehnung) -> HTTPException:
    return HTTPException(status_code=status_fuer(a.grund), detail={"grund": a.grund, "begruendung": a.begruendung})


def betrieb(request: Request) -> Betrieb:
    return request.app.state.betrieb


def vermittlung(request: Request) -> Vermittlung:
    return request.app.state.vermittlung


def verzeichnis(request: Request) -> Verzeichnis:
    return request.app.state.verzeichnis


def bus(request: Request) -> Ereignisbus:
    return request.app.state.bus


def konfig(request: Request) -> Konfig:
    return request.app.state.konfig


def herkunft(request: Request) -> str | None:
    return request.client.host if request.client else None


def nur_heimnetz(request: Request) -> None:
    """Oberfläche und Verwaltung nur aus erlaubten Netzen (Heimnetz, VPN). Der Server prüft selbst."""
    if not konfig(request).erlaubt(herkunft(request)):
        raise HTTPException(status_code=403, detail={"grund": "herkunft_nicht_erlaubt", "begruendung": "Nur aus dem Heimnetz oder über VPN erreichbar."})


def wer(request: Request) -> str:
    return f"oberflaeche {herkunft(request) or 'lokal'}"


def json_daten(obj: Any) -> Any:
    return obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj
