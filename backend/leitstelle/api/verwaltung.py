"""Eigene Schnittstelle `/api/*` für die Oberfläche: lesen seitenweise, steuern, einrichten.
Nur aus erlaubten Netzen; jede Ablehnung kommt mit Grundwort und Satz."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from .. import version
from ..fach import faehigkeitsprobe, regelwerk
from ..fach.fehler import Ablehnung
from ..fach.lagebild import lagebild
from ..fach.verzeichnis import AnwendungDaten, DienstAenderung, DienstDaten, KnotenDaten
from ..kern.werte import Auftragszustand, Betriebsmodus
from ..ports.ablage.eintraege import SteckbriefEintrag
from .gemeinsam import ablehnung_als_fehler, betrieb, geschrieben, nur_heimnetz, verzeichnis, wer

router = APIRouter(prefix="/api", dependencies=[Depends(nur_heimnetz)])


class HauptreglerDaten(BaseModel):
    modus: Betriebsmodus
    hintergrund: bool = True
    grund: str = Field(default="", max_length=300)


class StoppDaten(BaseModel):
    modus: Literal["sofort", "auslaufen"]
    grund: str = Field(default="", max_length=300)


class ErkennDaten(BaseModel):
    adresse: str = Field(min_length=8, max_length=255)
    zugang: str | None = Field(default=None, max_length=500)
    extern: bool = False


class SperrDaten(BaseModel):
    grund: str = Field(default="", max_length=300)


class FreigabeDaten(BaseModel):
    vorschau: bool = True


class AliasDaten(BaseModel):
    alias: str = Field(min_length=1, max_length=255)
    familie: str = Field(min_length=1, max_length=255)


async def _fachlich(aufruf):
    try:
        return await aufruf
    except Ablehnung as a:
        raise ablehnung_als_fehler(a) from a


@router.get("/version")
async def version_lesen():
    return {"version": version()}


@router.get("/lage")
async def lage(request: Request):
    return lagebild(betrieb(request))


@router.post("/hauptregler")
async def hauptregler(daten: HauptreglerDaten, request: Request):
    betroffen = await betrieb(request).hauptregler(daten.modus, daten.hintergrund, wer(request), daten.grund)
    return {"modus": daten.modus.value, "hintergrund": daten.hintergrund, "betroffene_auftraege": betroffen}


@router.get("/kennzahlen")
async def kennzahlen(request: Request):
    """Heute (seit Mitternacht, Ortszeit) abgeschlossene Aufträge."""
    from datetime import datetime
    mitternacht = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return await (await geschrieben(request)).auftraege.kennzahlen(mitternacht)


# ── Aufträge ─────────────────────────────────────────────────────────────
@router.get("/auftraege")
async def auftraege(request: Request, ab: int = Query(0, ge=0), anzahl: int = Query(50, ge=1, le=200),
                    anwendung: str | None = None, zustand: Auftragszustand | None = None):
    eintraege, gesamt = await (await geschrieben(request)).auftraege.seite(ab, anzahl, anwendung, zustand)
    return {"eintraege": eintraege, "gesamt": gesamt, "ab": ab, "anzahl": anzahl}


@router.get("/auftraege/{kennung}")
async def auftrag(kennung: str, request: Request):
    e = await (await geschrieben(request)).auftraege.holen(kennung)
    if e is None:
        raise ablehnung_als_fehler(Ablehnung("unbekannt", "Diesen Auftrag gibt es nicht."))
    return e


@router.post("/auftraege/{kennung}/stoppen")
async def stoppen(kennung: str, daten: StoppDaten, request: Request):
    await _fachlich(betrieb(request).stoppen(kennung, daten.modus == "sofort", daten.grund, wer(request)))
    return {"auftrag": kennung, "modus": daten.modus}


@router.get("/massnahmen")
async def massnahmen(request: Request, ab: int = Query(0, ge=0), anzahl: int = Query(50, ge=1, le=200)):
    eintraege, gesamt = await (await geschrieben(request)).massnahmen.neueste(anzahl, ab)
    return {"eintraege": eintraege, "gesamt": gesamt, "ab": ab, "anzahl": anzahl}


@router.get("/regelwerk")
async def regelwerk_lesen(request: Request) -> regelwerk.RegelwerkSicht:
    """Maßnahmen und Regelwerte je Gruppe, mit Erklärung, Einheit, Vorgabe ab Werk und Grenzen für Änderungen von Hand."""
    return regelwerk.sicht(betrieb(request).verbund.regelwerk)


@router.patch("/regelwerk")
async def regelwerk_aendern(daten: regelwerk.RegelwerkAenderung, request: Request) -> regelwerk.RegelwerkSicht:
    """Maßnahmen schalten und Regelwerte ändern; was fehlt, bleibt. Gespeichert wird nur, was von der Vorgabe abweicht; jede
    Änderung steht mit alt und neu im Prüfprotokoll und wirkt sofort."""
    return await _fachlich(regelwerk.aendern(betrieb(request), daten, wer(request)))


@router.put("/steckbriefe")
async def steckbrief_setzen(daten: SteckbriefEintrag, request: Request):
    """Von Hand, was der Dienst nicht selbst sagt; geht seiner Auskunft vor. Alles leer entfernt den Eintrag."""
    await _fachlich(betrieb(request).steckbrief_setzen(daten, wer(request)))
    return daten


@router.get("/bewegungen")
async def bewegungen(request: Request, ab: int = Query(0, ge=0), anzahl: int = Query(50, ge=1, le=200)):
    """Laden und Entladen als Rohdaten, neueste zuerst."""
    eintraege, gesamt = await (await geschrieben(request)).bewegungen.neueste(anzahl, ab)
    return {"eintraege": eintraege, "gesamt": gesamt, "ab": ab, "anzahl": anzahl}


@router.get("/pruefprotokoll")
async def pruefprotokoll(request: Request, anzahl: int = Query(100, ge=1, le=500)):
    return {"eintraege": await betrieb(request).ablage.pruefung.neueste(anzahl)}


# ── Modelle und Speicher ─────────────────────────────────────────────────
@router.post("/modelle/{kennung}/laden")
async def laden(kennung: str, request: Request):
    if kennung not in betrieb(request).verbund.modelle:
        raise ablehnung_als_fehler(Ablehnung("unbekannt", "Dieses Modell gibt es nicht."))
    await _fachlich(betrieb(request).modell_von_hand(kennung, True, wer(request)))
    return {"modell": kennung, "aktion": "laden"}


@router.post("/modelle/{kennung}/entladen")
async def entladen(kennung: str, request: Request):
    if kennung not in betrieb(request).verbund.modelle:
        raise ablehnung_als_fehler(Ablehnung("unbekannt", "Dieses Modell gibt es nicht."))
    await _fachlich(betrieb(request).modell_von_hand(kennung, False, wer(request)))
    return {"modell": kennung, "aktion": "entladen"}


@router.post("/knoten/{kennung}/speicher_freigeben")
async def speicher_freigeben(kennung: str, daten: FreigabeDaten, request: Request):
    plan = await _fachlich(betrieb(request).speicher_freigeben(kennung, daten.vorschau, wer(request)))
    return {"vorschau": daten.vorschau, "plan": plan, "frei_gb": round(sum(f.gb for f in plan if f.darf), 2)}


@router.post("/knoten/{kennung}/schlaf_beenden")
async def schlaf_beenden(kennung: str, request: Request):
    """"Nicht mehr warten": der Rechner gilt nicht mehr als schlafend; seine Dienste werden sofort wieder geprüft."""
    await _fachlich(betrieb(request).schlaf_beenden(kennung, wer(request)))
    return {"knoten": kennung, "schlaeft": False}


@router.post("/knoten/{kennung}/laeufer/{pid}/beenden")
async def laeufer_prozess_beenden(kennung: str, pid: int, request: Request):
    """"Prozess beenden": einen Arbeiter des Läufers, der ohne Auftrag rechnet, vom Maschinenraum beenden lassen (Rückfall
    per Hand zur Regel "Läufer arbeitet ohne Auftrag", dieselbe Prüfung)."""
    e = await _fachlich(betrieb(request).laeufer_prozess_beenden_von_hand(kennung, pid, wer(request)))
    return {"knoten": kennung, "pid": pid, "erfolg": e.erfolg, "meldung": e.meldung}


@router.post("/aliasse")
async def alias_setzen(daten: AliasDaten, request: Request):
    await _fachlich(verzeichnis(request).alias_setzen(daten.alias, daten.familie, wer(request)))
    return daten


@router.delete("/aliasse/{alias:path}")
async def alias_loeschen(alias: str, request: Request):
    await _fachlich(verzeichnis(request).alias_loeschen(alias, wer(request)))
    return {"alias": alias}


# ── Rechner und Dienste ──────────────────────────────────────────────────
def _knoten_ohne_geheimnis(e):
    return e.model_dump(mode="json", exclude={"agent_geheim", "agent_fingerabdruck"}) | {"agent_schluessel": e.agent_fingerabdruck is not None}


@router.post("/knoten")
async def knoten_anlegen(daten: KnotenDaten, request: Request):
    return _knoten_ohne_geheimnis(await _fachlich(verzeichnis(request).knoten_anlegen(daten, wer(request))))


@router.put("/knoten/{kennung}")
async def knoten_aendern(kennung: str, daten: KnotenDaten, request: Request):
    return _knoten_ohne_geheimnis(await _fachlich(verzeichnis(request).knoten_aendern(kennung, daten, wer(request))))


@router.delete("/knoten/{kennung}")
async def knoten_loeschen(kennung: str, request: Request):
    await _fachlich(verzeichnis(request).knoten_loeschen(kennung, wer(request)))
    return {"knoten": kennung}


@router.post("/knoten/{kennung}/agent/schluessel")
async def agent_schluessel_zeigen(kennung: str, request: Request):
    return {"schluessel": await _fachlich(verzeichnis(request).agent_schluessel_zeigen(kennung, wer(request)))}


@router.post("/knoten/{kennung}/agent/schluessel/neu")
async def agent_schluessel_neu(kennung: str, request: Request):
    return {"schluessel": await _fachlich(verzeichnis(request).agent_schluessel_neu(kennung, wer(request)))}


@router.post("/dienste/erkennen")
async def dienst_erkennen(daten: ErkennDaten, request: Request):
    return await _fachlich(verzeichnis(request).erkennen(daten.adresse, daten.zugang, daten.extern))


def _dienst_ohne_geheimnis(e):
    return e.model_dump(mode="json", exclude={"zugang_geheim"}) | {"zugang": e.zugang_geheim is not None}


@router.post("/dienste")
async def dienst_anlegen(daten: DienstDaten, request: Request):
    return _dienst_ohne_geheimnis(await _fachlich(verzeichnis(request).dienst_anlegen(daten, wer(request))))


@router.patch("/dienste/{kennung}")
async def dienst_aendern(kennung: str, daten: DienstAenderung, request: Request):
    return _dienst_ohne_geheimnis(await _fachlich(verzeichnis(request).dienst_aendern(kennung, daten, wer(request))))


@router.post("/dienste/{kennung}/pruefen")
async def dienst_pruefen(kennung: str, request: Request):
    """Jetzt prüfen: fragt den Dienst sofort, auch im Ausfall (sonst in wachsenden Abständen)."""
    zustand = await _fachlich(betrieb(request).dienst_pruefen(kennung, wer(request)))
    return {"dienst": kennung, "zustand": zustand}


@router.post("/dienste/{kennung}/faehigkeiten_pruefen")
async def faehigkeiten_pruefen(kennung: str, request: Request) -> list[faehigkeitsprobe.Probenergebnis]:
    """Fähigkeitsprobe von Hand (externe Anbieter): je Modell eine kleine Aufgabe, etwa ein Bild mit einer Frage; zählt gegen
    die Grenzen des Anbieters. Belegte und nicht belegte Fähigkeiten stehen danach mit Zeitpunkt im Steckbrief."""
    return await _fachlich(faehigkeitsprobe.pruefen(betrieb(request), kennung, wer(request)))


@router.delete("/dienste/{kennung}")
async def dienst_loeschen(kennung: str, request: Request):
    await _fachlich(verzeichnis(request).dienst_loeschen(kennung, wer(request)))
    return {"dienst": kennung}


@router.post("/dienste/{kennung}/zugang")
async def dienst_zugang(kennung: str, request: Request):
    return {"zugang": await _fachlich(verzeichnis(request).dienst_zugang_zeigen(kennung, wer(request)))}


# ── Anwendungen ──────────────────────────────────────────────────────────
@router.post("/anwendungen")
async def anwendung_anlegen(daten: AnwendungDaten, request: Request):
    a, schluessel = await _fachlich(verzeichnis(request).anwendung_anlegen(daten, wer(request)))
    return {"kennung": a.kennung, "name": a.name, "schluessel": schluessel}


@router.put("/anwendungen/{kennung}")
async def anwendung_aendern(kennung: str, daten: AnwendungDaten, request: Request):
    a = await _fachlich(verzeichnis(request).anwendung_aendern(kennung, daten, wer(request)))
    return {"kennung": a.kennung, "name": a.name}


@router.delete("/anwendungen/{kennung}")
async def anwendung_loeschen(kennung: str, request: Request):
    await _fachlich(verzeichnis(request).anwendung_loeschen(kennung, wer(request)))
    return {"anwendung": kennung}


@router.post("/anwendungen/{kennung}/schluessel")
async def schluessel_zeigen(kennung: str, request: Request):
    return {"schluessel": await _fachlich(verzeichnis(request).anwendung_schluessel_zeigen(kennung, wer(request)))}


@router.post("/anwendungen/{kennung}/schluessel/neu")
async def schluessel_neu(kennung: str, request: Request):
    return {"schluessel": await _fachlich(verzeichnis(request).anwendung_schluessel_neu(kennung, wer(request)))}


@router.post("/anwendungen/{kennung}/sperren")
async def sperren(kennung: str, daten: SperrDaten, request: Request):
    await _fachlich(verzeichnis(request).anwendung_sperren(kennung, daten.grund, wer(request)))
    return {"anwendung": kennung, "gesperrt": True}


@router.post("/anwendungen/{kennung}/freigeben")
async def freigeben(kennung: str, request: Request):
    await _fachlich(verzeichnis(request).anwendung_freigeben(kennung, wer(request)))
    return {"anwendung": kennung, "gesperrt": False}
