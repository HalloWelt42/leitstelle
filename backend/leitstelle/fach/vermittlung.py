"""Vermittlung: ein Aufruf der Fassade wird zum Auftrag, wartet mit Hinweisen und wird durchgeleitet.

Die Anfrage geht unverändert an den Dienst, nur `model` wird durch den Namen ersetzt, unter dem der
Dienst das zugeteilte Modell kennt. Die Antwort geht unverändert zurück. Gemessen werden Zeit bis
zum ersten Stück, Token und bei Abbruch die Länge des Teiltextes.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..kern.modelle import Auftrag
from ..kern.werte import Auftragszustand, Faehigkeit, Modellzustand, Prioritaet
from ..konfig import Konfig
from ..ports.dienste import DienstFehler, Durchleitung, Strom
from .betrieb import Betrieb, Lauf, Messung
from .fehler import Ablehnung

NEUVERSUCHE_NICHT_GELADEN = 2       # Dienst hat das Modell zwischen Abgleich und Anfrage selbst entladen
NEUVERSUCHE_UEBERLAST = 3           # Dienst meldete zu viele Anfragen (429): gesperrt, Auftrag wartet oder weicht aus
UEBERLAST_WARTE_S = 60.0            # Sperre, wenn der Dienst kein Retry-After nennt


def warte_s_aus(kopf: dict[str, str]) -> float:
    """Retry-After in Sekunden (die Datumsform kommt bei Anbietern im OpenAI-Format nicht vor)."""
    wert = next((w for k, w in kopf.items() if k.lower() == "retry-after"), "")
    try:
        return max(1.0, float(wert))
    except ValueError:
        return UEBERLAST_WARTE_S


class _Abbruch(Exception):
    pass


class _Neuversuch(Exception):
    pass


@dataclass
class Wartet:
    begruendung: str
    voraussichtlich_s: float | None


@dataclass
class Vorgang:
    auftrag: Auftrag
    lauf: Lauf
    messung: Messung = field(default_factory=Messung)
    abgeschlossen: bool = False
    neuversuche: int = 0
    modellname: str = ""
    knoten: str | None = None
    start_s: float = 0.0              # Beginn der Durchleitung, für die Zeit bis zum ersten Stück


def _fehler_json(grund: str, text: str) -> dict[str, Any]:
    return {"error": {"message": text, "type": "leitstelle", "code": grund}}


class Vermittlung:
    def __init__(self, betrieb: Betrieb, konfig: Konfig) -> None:
        self.betrieb = betrieb
        self.konfig = konfig

    # ── Annehmen ─────────────────────────────────────────────────────────
    def annehmen(self, anwendung: str, faehigkeit: Faehigkeit, modellwunsch: str | None, prioritaet: Prioritaet | None, titel: str,
                 arbeit: str | None = None) -> Vorgang:
        familie = None
        if modellwunsch and modellwunsch not in ("auto", "leitstelle"):
            familie = self.betrieb.familie_fuer(modellwunsch)
            if familie is None:
                raise self.betrieb.unbekannt(modellwunsch)
        auftrag, lauf = self.betrieb.anlegen(anwendung, faehigkeit, familie, prioritaet, titel, arbeit)
        v = Vorgang(auftrag=auftrag, lauf=lauf)
        if lauf.ende.is_set():                         # sofort abgelehnt (Rechte, Zone, kein Modell)
            self._abschliessen(v, Auftragszustand.ABGELEHNT, lauf.grund, lauf.begruendung)
            raise Ablehnung(lauf.grund or "kein_dienst", lauf.begruendung)
        return v

    def _abschliessen(self, v: Vorgang, zustand: Auftragszustand, grund: str | None = None, begruendung: str | None = None) -> None:
        if not v.abgeschlossen:
            v.abgeschlossen = True
            self.betrieb.abschliessen(v.auftrag.kennung, zustand, v.messung, grund, begruendung)

    def aufraeumen(self, v: Vorgang) -> None:
        """Aufruf beendet, ohne dass der Auftrag abgeschlossen wurde: die Anwendung ist weg."""
        self._abschliessen(v, Auftragszustand.ABGEBROCHEN, "anwendung", "Die Anwendung hat die Verbindung getrennt.")

    # ── Warten ───────────────────────────────────────────────────────────
    async def warten(self, v: Vorgang, getrennt: Callable[[], Awaitable[bool]] | None = None) -> AsyncIterator[Wartet]:
        """Bis Modell und Platz bereit sind; gibt alle `hinweis_s` den Stand. Ablehnung oder Abbruch als `Ablehnung`."""
        lauf = v.lauf
        seit_hinweis = 0.0
        while not lauf.freigabe.is_set():
            if lauf.ende.is_set():
                a = v.auftrag
                zustand = Auftragszustand.ABGELEHNT if a.zustand == Auftragszustand.ABGELEHNT else Auftragszustand.ABGEBROCHEN
                self._abschliessen(v, zustand, lauf.grund, lauf.begruendung)
                raise Ablehnung(lauf.grund or "nutzer", lauf.begruendung)
            warte_auf = [asyncio.ensure_future(lauf.freigabe.wait()), asyncio.ensure_future(lauf.ende.wait())]
            fertig, offen = await asyncio.wait(warte_auf, timeout=1.0, return_when=asyncio.FIRST_COMPLETED)
            for t in offen:
                t.cancel()
            if fertig:
                continue
            seit_hinweis += 1.0
            if getrennt and await getrennt():
                self.aufraeumen(v)
                raise Ablehnung("anwendung", "Die Anwendung hat die Verbindung getrennt.")
            if seit_hinweis >= self.konfig.hinweis_s:
                seit_hinweis = 0.0
                yield Wartet(v.auftrag.begruendung, v.auftrag.voraussichtlich_s)

    async def _bis_ende(self, aufgabe: Awaitable[Any], lauf: Lauf) -> Any:
        t = asyncio.ensure_future(aufgabe)
        e = asyncio.ensure_future(lauf.ende.wait())
        fertig, _ = await asyncio.wait({t, e}, return_when=asyncio.FIRST_COMPLETED)
        if t in fertig:
            e.cancel()
            return t.result()
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
        raise _Abbruch()

    # ── Durchleiten ──────────────────────────────────────────────────────
    async def durchleiten(self, v: Vorgang, pfad: str, koerper: dict[str, Any], strom: bool) -> AsyncIterator[bytes]:
        """Liefert bei Strom die SSE-Zeilen, sonst einmal den ganzen Körper (JSON). Fehler des Dienstes werden
        als Fehler im OpenAI-Format geliefert; `v.messung` und der Auftrag werden abgeschlossen."""
        b = self.betrieb
        a = v.auftrag
        ort = b.ort(a.modell or "")
        modell = b.verbund.modelle.get(a.modell or "")
        v.modellname = modell.name if modell else ort.schluessel
        v.knoten = a.knoten
        anfrage = {**koerper, "model": ort.anfragename}
        start = b.uhr.jetzt()
        try:
            antwort = await self._bis_ende(b.adapter[a.dienst or ""].anfrage(pfad, anfrage), v.lauf)
        except _Abbruch:
            yield self._abbruch_ende(v, strom)
            return
        except DienstFehler as f:
            if f.grund == "dienst_nicht_erreichbar":
                b.dienst_gestoert(a.dienst or "", f.meldung)
            self._abschliessen(v, Auftragszustand.FEHLGESCHLAGEN, f.grund, f.meldung)
            yield self._fehler(strom, f.grund, f.meldung)
            return
        try:
            if antwort.status == 429 and v.neuversuche < NEUVERSUCHE_UEBERLAST:
                b.dienst_ueberlastet(a.dienst or "", warte_s_aus(antwort.kopf))
                self._zurueckstellen(v)
                raise _Neuversuch()
            if antwort.status >= 400:
                text = (await antwort.lesen()).decode("utf-8", "replace")
                if self._nicht_geladen(text) and v.neuversuche < NEUVERSUCHE_NICHT_GELADEN:
                    self._neu_einreihen(v)
                    raise _Neuversuch()
                self._abschliessen(v, Auftragszustand.FEHLGESCHLAGEN, "dienst_fehler", text[:500])
                yield self._fehler(strom, "dienst_fehler", text[:500])
                return
            if not strom:
                roh = await self._bis_ende(antwort.lesen(), v.lauf)
                v.messung.erstes_stueck_s = b.uhr.jetzt() - start
                self._usage(v, roh)
                self._abschliessen(v, Auftragszustand.FERTIG)
                yield roh
                return
            # Abbruch schließt den Strom von außen (Lauf.abbrecher); die Schleife liest ohne Zusatzaufwand je Stück
            v.lauf.abbrecher = lambda: self.betrieb._nebenbei(antwort.schliessen())
            if v.lauf.ende.is_set():
                raise _Abbruch()
            try:
                async for zeile in antwort.zeilen():
                    if zeile.startswith(b"data: ") and zeile != b"data: [DONE]":
                        self._stueck_messen(v, zeile[6:], start)
                    yield zeile + b"\n"
            except DienstFehler as f:
                if not v.lauf.ende.is_set():
                    self._abschliessen(v, Auftragszustand.FEHLGESCHLAGEN, f.grund, f.meldung)
                    yield self._fehler(strom, f.grund, f.meldung)
                    return
            finally:
                v.lauf.abbrecher = None
            if v.lauf.ende.is_set():
                raise _Abbruch()
            self._abschliessen(v, Auftragszustand.FERTIG)
        except _Abbruch:
            yield self._abbruch_ende(v, strom)
        finally:
            await antwort.schliessen()

    @staticmethod
    def _nicht_geladen(text: str) -> bool:
        t = text.lower()
        return "not loaded" in t or "no models loaded" in t or "has been unloaded" in t

    def _neu_einreihen(self, v: Vorgang) -> None:
        """Der Dienst kennt das Modell nicht mehr als geladen: Modell als frei werten, Auftrag zurück in die Warteschlange."""
        m = self.betrieb.verbund.modelle.get(v.auftrag.modell or "")
        if m is not None:
            m.zustand = Modellzustand.FREI
            m.geladen_seit_s = None
            self.betrieb.melden(f"{m.name} war beim Dienst nicht mehr geladen; der Auftrag wird neu eingereiht")
        self._zurueckstellen(v)

    def _zurueckstellen(self, v: Vorgang) -> None:
        """Auftrag zurück in die Warteschlange; der Zuteiler wählt neu (anderer Platz, anderes Modell oder warten)."""
        b = self.betrieb
        a = v.auftrag
        v.neuversuche += 1
        m = b.verbund.modelle.get(a.modell or "")
        if m is not None:
            m.auftraege_aktiv = max(0, m.auftraege_aktiv - 1)
            if m.auftraege_aktiv == 0 and m.zustand == Modellzustand.RECHNET:
                m.zustand = Modellzustand.GELADEN
        a.zustand = Auftragszustand.EINGEREIHT
        a.dienst = a.modell = a.knoten = None
        a.start_s = None
        v.lauf.freigabe.clear()
        b.anstossen()

    def _stueck_messen(self, v: Vorgang, daten: bytes, start: float) -> None:
        try:
            teil = json.loads(daten)
        except ValueError:
            return
        for wahl in teil.get("choices") or []:
            delta = wahl.get("delta") or {}
            inhalt = (delta.get("content") or "") + (delta.get("reasoning_content") or delta.get("reasoning") or "")
            if inhalt:
                if v.messung.erstes_stueck_s is None:
                    v.messung.erstes_stueck_s = self.betrieb.uhr.jetzt() - start
                v.messung.teilergebnis_zeichen += len(inhalt)
        if teil.get("usage"):
            v.messung.token_ein = teil["usage"].get("prompt_tokens")
            v.messung.token_aus = teil["usage"].get("completion_tokens")

    def _usage(self, v: Vorgang, roh: bytes) -> None:
        try:
            daten = json.loads(roh)
        except ValueError:
            return
        usage = daten.get("usage") or {}
        v.messung.token_ein = usage.get("prompt_tokens")
        v.messung.token_aus = usage.get("completion_tokens")

    def _abbruch_ende(self, v: Vorgang, strom: bool) -> bytes:
        lauf = v.lauf
        self._abschliessen(v, Auftragszustand.ABGEBROCHEN, lauf.grund or "nutzer", lauf.begruendung)
        if not strom:
            return json.dumps(_fehler_json(lauf.grund or "nutzer", lauf.begruendung)).encode()
        ende = {"id": f"leitstelle-{v.auftrag.kennung}", "object": "chat.completion.chunk", "model": v.modellname,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "leitstelle_abbruch"}],
                "x-leitstelle": {"grund": lauf.grund, "begruendung": lauf.begruendung, "teilergebnis_zeichen": v.messung.teilergebnis_zeichen}}
        return f"data: {json.dumps(ende, ensure_ascii=False)}\n\ndata: [DONE]\n\n".encode()

    @staticmethod
    def _fehler(strom: bool, grund: str, text: str) -> bytes:
        daten = json.dumps(_fehler_json(grund, text), ensure_ascii=False)
        return f"data: {daten}\n\ndata: [DONE]\n\n".encode() if strom else daten.encode()

    # ── Allgemeine Durchleitung (Dienste mit eigener Schnittstelle) ──────
    def faehigkeit_fuer(self, anwendung: str, familie: str) -> Faehigkeit:
        """Unter welcher Fähigkeit ein Aufruf an ein bestimmtes Modell läuft: die erste, die Modell und Anwendung teilen."""
        a = self.betrieb.verbund.anwendungen.get(anwendung)
        faehig = set().union(*(m.faehigkeiten for m in self.betrieb.verbund.modelle.values() if m.familie == familie)) if a else set()
        gemeinsam = [f for f in Faehigkeit if f in faehig and a and f in a.faehigkeiten]
        if not gemeinsam:
            raise Ablehnung("faehigkeit_nicht_erlaubt", f"Die Anwendung darf {familie} nicht nutzen (keine gemeinsame Fähigkeit).")
        return gemeinsam[0]

    async def roh_anfragen(self, v: Vorgang, d: Durchleitung) -> Strom:
        """Nach der Freigabe: Anfrage unverändert an den zugeteilten Dienst. Fehler schließen den Auftrag ab."""
        b = self.betrieb
        a = v.auftrag
        modell = b.verbund.modelle.get(a.modell or "")
        v.modellname, v.knoten = (modell.name if modell else ""), a.knoten
        v.messung = Messung()
        v.start_s = b.uhr.jetzt()
        try:
            return await self._bis_ende(b.adapter[a.dienst or ""].durchleiten(b.ort(a.modell or "").schluessel, d), v.lauf)
        except _Abbruch:
            self._abschliessen(v, Auftragszustand.ABGEBROCHEN, v.lauf.grund or "nutzer", v.lauf.begruendung)
            raise Ablehnung(v.lauf.grund or "nutzer", v.lauf.begruendung) from None
        except DienstFehler as f:
            self._abschliessen(v, Auftragszustand.FEHLGESCHLAGEN, f.grund, f.meldung)
            raise Ablehnung(f.grund, f.meldung) from None

    async def roh_strom(self, v: Vorgang, antwort: Strom) -> AsyncIterator[bytes]:
        """Die Antwort des Dienstes, wie sie kommt; am Ende wird der Auftrag mit dem Ergebnis abgeschlossen."""
        b = self.betrieb
        v.lauf.abbrecher = lambda: b._nebenbei(antwort.schliessen())
        try:
            async for stueck in antwort.stuecke():
                if v.messung.erstes_stueck_s is None:
                    v.messung.erstes_stueck_s = b.uhr.jetzt() - v.start_s
                yield stueck
            if v.lauf.ende.is_set():
                self._abschliessen(v, Auftragszustand.ABGEBROCHEN, v.lauf.grund or "nutzer", v.lauf.begruendung)
            elif antwort.status >= 400:
                self._abschliessen(v, Auftragszustand.FEHLGESCHLAGEN, "dienst_fehler", f"Der Dienst antwortet mit {antwort.status}.")
            else:
                self._abschliessen(v, Auftragszustand.FERTIG)
        except DienstFehler as f:
            self._abschliessen(v, Auftragszustand.FEHLGESCHLAGEN, f.grund, f.meldung)
        finally:
            # erst abschließen, dann schließen: reißt die Anwendung ab, wird dieser Rest abgebrochen, und jedes weitere
            # `await` kann selbst abgebrochen werden; der Auftrag braucht seinen Endzustand trotzdem
            v.lauf.abbrecher = None
            self.aufraeumen(v)
            await antwort.schliessen()

    async def ausfuehren(self, v: Vorgang, pfad: str, koerper: dict[str, Any], strom: bool,
                         getrennt: Callable[[], Awaitable[bool]] | None = None) -> AsyncIterator[bytes | Wartet]:
        """Warten und Durchleiten in einem, mit Neuversuch, wenn der Dienst das Modell inzwischen selbst entladen hat."""
        while True:
            async for w in self.warten(v, getrennt):
                yield w
            try:
                async for teil in self.durchleiten(v, pfad, koerper, strom):
                    yield teil
                return
            except _Neuversuch:
                continue
