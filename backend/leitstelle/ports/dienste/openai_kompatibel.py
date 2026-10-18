"""Adapter für Modell-Läufer im OpenAI-Format.

Steuerbar, wenn die Gegenstelle die native Schnittstelle `/api/v1/models` mit Laden und Entladen kennt:
dann meldet sie echten Ladezustand, Größe, Parameterzahl und Instanzen. Sonst nur die OpenAI-Liste
`/v1/models`; die Leitstelle behandelt die Modelle dann als immer verfügbar und steuert keinen Speicher.

Gelernt am echten Läufer (siehe Gedächtnis): Entladen braucht die Instanz-Kennung, nicht den Schlüssel;
"geladen" heißt `loaded_instances` nicht leer; Speichermangel kommt als Fehlertext mit "insufficient".
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from ...kern.werte import GIB, Eignung
from ...kern.werte import Faehigkeit as F
from ...protokoll.knoten import Selbstauskunft
from .schnittstelle import Dienstbericht, DienstFehler, Durchleitung, ModellBericht

TEXT_FAEHIGKEITEN = {F.TEXT, F.UEBERSETZEN}


def _milliarden(params: str | None) -> float | None:
    """'80B' -> 80, '567M' -> 0.567, None -> None."""
    if not params:
        return None
    t = re.fullmatch(r"\s*([\d.]+)\s*([BMK])\s*", params.upper())
    if not t:
        return None
    zahl = float(t.group(1))
    return {"B": zahl, "M": zahl / 1000, "K": zahl / 1_000_000}[t.group(2)]


def _faehigkeiten(typ: str, faehig: dict | None) -> tuple[set[F], bool]:
    if typ.startswith("embedding"):
        return {F.EINBETTUNG}, True
    f = set(TEXT_FAEHIGKEITEN)
    faehig = faehig or {}
    if faehig.get("vision") or typ == "vlm":
        f.add(F.BILD_BESCHREIBEN)
    if faehig.get("trained_for_tool_use"):
        f.add(F.WERKZEUG)
    return f, False


def _auskunft(m: dict[str, Any]) -> Selbstauskunft:
    """Was der Modell-Läufer über ein Modell sagt: Beschreibung der Modellkarte, schrittweises Schließen (`reasoning`),
    Quantisierung. Kontext, Parameter, Bilder und Werkzeuge stehen schon im Bericht."""
    faehig = m.get("capabilities") or {}
    quant = m.get("quantization") or {}
    return Selbstauskunft(zweck=str(m.get("description") or "").strip(), eignung=[Eignung.DENKEN] if faehig.get("reasoning") else [],
                          quantisierung=quant.get("name") if isinstance(quant, dict) else None)


def _fehlertext(roh: bytes) -> str:
    try:
        daten = json.loads(roh)
    except ValueError:
        return roh.decode("utf-8", "replace")[:500]
    fehler = daten.get("error") if isinstance(daten, dict) else None
    if isinstance(fehler, dict):
        return str(fehler.get("message", fehler))
    return str(fehler or daten)[:500]


class HttpStrom:
    """Durchgeleitete Antwort. `schliessen()` darf von außen kommen, während jemand liest (Abbruch):
    die Iteration endet dann still, statt einen Fehler zu werfen."""

    def __init__(self, antwort: httpx.Response) -> None:
        self._antwort = antwort
        self._geschlossen = False
        self.status = antwort.status_code
        self.kopf = {k.lower(): v for k, v in antwort.headers.items()}

    async def zeilen(self) -> AsyncIterator[bytes]:
        try:
            async for zeile in self._antwort.aiter_lines():
                yield zeile.encode("utf-8")
        except Exception as fehler:
            if self._geschlossen:
                return
            raise DienstFehler("dienst_nicht_erreichbar", f"Strom abgerissen: {type(fehler).__name__} {fehler}".strip(), wiederholbar=False) from fehler

    async def stuecke(self) -> AsyncIterator[bytes]:
        """Die Antwort, wie sie kommt (auch Binärdaten wie Audio)."""
        try:
            async for stueck in self._antwort.aiter_raw():
                yield stueck
        except Exception as fehler:
            if self._geschlossen:
                return
            raise DienstFehler("dienst_nicht_erreichbar", f"Strom abgerissen: {type(fehler).__name__} {fehler}".strip(), wiederholbar=False) from fehler

    async def lesen(self) -> bytes:
        return await self._antwort.aread()

    async def schliessen(self) -> None:
        self._geschlossen = True
        await self._antwort.aclose()


class OpenAIKompatibel:
    meldet_sich_selbst = False           # die Leitstelle fragt nach dem Zustand (mit wachsenden Abständen bei Ausfall)

    def __init__(self, adresse: str, zugang: str | None = None, verbindung_s: float = 10.0, transport: httpx.AsyncBaseTransport | None = None,
                 beim_senden: Callable[[], None] | None = None) -> None:
        basis = adresse.rstrip("/")
        if basis.endswith("/v1"):
            basis = basis[:-3]
        kopf = {"Authorization": f"Bearer {zugang}"} if zugang else {}
        self._kurz = httpx.Timeout(verbindung_s)
        self._beim_senden = beim_senden
        # Arbeit (Laden, Antworten) ohne Lese-Grenze, nur Verbindungsaufbau begrenzt; jede Anfrage wird gezählt
        self._client = httpx.AsyncClient(base_url=basis, headers=kopf, transport=transport,
                                         timeout=httpx.Timeout(connect=verbindung_s, read=None, write=None, pool=None),
                                         event_hooks={"request": [self._gesendet]} if beim_senden else {})

    async def _gesendet(self, _anfrage: httpx.Request) -> None:
        if self._beim_senden:
            self._beim_senden()

    async def schliessen(self) -> None:
        await self._client.aclose()

    # ── Zustand, ohne etwas zu verändern ─────────────────────────────────
    async def zustand(self) -> Dienstbericht:
        try:
            r = await self._client.get("/api/v1/models", timeout=self._kurz)
            if r.status_code == 200 and isinstance(r.json(), dict) and "models" in r.json():
                return Dienstbericht(erreichbar=True, steuerbar=True, modelle=[self._nativ(m) for m in r.json()["models"]])
            r = await self._client.get("/v1/models", timeout=self._kurz)
            if r.status_code == 200:
                return Dienstbericht(erreichbar=True, steuerbar=False, modelle=[self._einfach(m) for m in r.json().get("data", [])],
                                     meldung="nur OpenAI-Liste: Laden und Entladen übernimmt der Dienst selbst")
            return Dienstbericht(erreichbar=False, meldung=f"Antwort {r.status_code}: {_fehlertext(r.content)}")
        except (httpx.HTTPError, ValueError) as fehler:
            return Dienstbericht(erreichbar=False, meldung=f"nicht erreichbar: {type(fehler).__name__} {fehler}".strip())

    @staticmethod
    def _nativ(m: dict[str, Any]) -> ModellBericht:
        faehigkeiten, einbettung = _faehigkeiten(str(m.get("type", "llm")), m.get("capabilities"))
        instanzen = m.get("loaded_instances") or []
        parallel = [int(i.get("config", {}).get("parallel")) for i in instanzen if i.get("config", {}).get("parallel")]
        return ModellBericht(
            schluessel=m["key"], name=m.get("display_name") or m["key"], faehigkeiten=faehigkeiten,
            gb=round((m.get("size_bytes") or 0) / GIB, 2), parameter_mrd=_milliarden(m.get("params_string")),
            geladen=bool(instanzen), instanzen=[i["id"] for i in instanzen if i.get("id")], plaetze=max(parallel) if parallel else None,
            kontext=m.get("max_context_length"), einbettung=einbettung, selbstauskunft=_auskunft(m))

    @staticmethod
    def _einfach(m: dict[str, Any]) -> ModellBericht:
        kennung = str(m["id"])
        einbettung = "embed" in kennung.lower()
        return ModellBericht(schluessel=kennung, name=kennung, faehigkeiten={F.EINBETTUNG} if einbettung else set(TEXT_FAEHIGKEITEN),
                             gb=0.0, geladen=True, instanzen=[kennung], einbettung=einbettung)

    # ── Steuern ──────────────────────────────────────────────────────────
    async def laden(self, schluessel: str) -> str:
        try:
            r = await self._client.post("/api/v1/models/load", json={"model": schluessel})
        except httpx.HTTPError as fehler:
            raise DienstFehler("dienst_nicht_erreichbar", f"{type(fehler).__name__} {fehler}".strip(), wiederholbar=True) from fehler
        if r.status_code >= 400:
            text = _fehlertext(r.content)
            if "insufficient" in text.lower() or "memory" in text.lower():
                raise DienstFehler("modell_passt_nicht", text, wiederholbar=True)
            raise DienstFehler("dienst_fehler", text)
        daten = r.json()
        return str(daten.get("instance_id") or schluessel)

    async def entladen(self, instanz: str) -> None:
        try:
            r = await self._client.post("/api/v1/models/unload", json={"instance_id": instanz}, timeout=self._kurz)
        except httpx.HTTPError as fehler:
            raise DienstFehler("dienst_nicht_erreichbar", f"{type(fehler).__name__} {fehler}".strip(), wiederholbar=True) from fehler
        if r.status_code >= 400:
            raise DienstFehler("dienst_fehler", _fehlertext(r.content))

    # ── Durchleiten ──────────────────────────────────────────────────────
    async def anfrage(self, pfad: str, koerper: dict[str, Any]) -> HttpStrom:
        try:
            antwort = await self._client.send(self._client.build_request("POST", pfad, json=koerper), stream=True)
        except httpx.HTTPError as fehler:
            raise DienstFehler("dienst_nicht_erreichbar", f"{type(fehler).__name__} {fehler}".strip(), wiederholbar=True) from fehler
        return HttpStrom(antwort)

    async def durchleiten(self, schluessel: str, d: Durchleitung) -> HttpStrom:
        """Allgemeiner Weg an den Läufer; der Modellschlüssel spielt hier keine Rolle (die Anfrage nennt ihr Modell selbst)."""
        url = httpx.URL("/" + d.pfad.lstrip("/"), query=d.abfrage.encode())
        try:
            antwort = await self._client.send(self._client.build_request(d.methode, url, headers=d.kopf, content=d.inhalt), stream=True)
        except httpx.HTTPError as fehler:
            raise DienstFehler("dienst_nicht_erreichbar", f"{type(fehler).__name__} {fehler}".strip(), wiederholbar=True) from fehler
        return HttpStrom(antwort)


def _milliarden_im_namen(kennung: str) -> float | None:
    """'Qwen/Qwen3.6-35B-A3B' -> 35, 'Qwen3.8-27B' -> 27: die Gesamtzahl, nicht die aktive (A3B)."""
    t = re.search(r"(?<![A-Za-z])(\d+(?:\.\d+)?)\s*([BM])(?![A-Za-z])", kennung.upper())
    return _milliarden(t.group(1) + t.group(2)) if t else None


class GesammelteAntwort:
    """Eine ganze Antwort, die der Adapter aus einem Strom des Anbieters zusammengesetzt hat (die Anwendung wollte keinen
    Strom). Verhält sich wie ein Strom mit einem einzigen Stück."""

    def __init__(self, inhalt: bytes) -> None:
        self._inhalt = inhalt
        self.status = 200
        self.kopf = {"content-type": "application/json"}

    async def zeilen(self) -> AsyncIterator[bytes]:
        for zeile in self._inhalt.splitlines():
            yield zeile

    async def stuecke(self) -> AsyncIterator[bytes]:
        yield self._inhalt

    async def lesen(self) -> bytes:
        return self._inhalt

    async def schliessen(self) -> None:
        return None


async def strom_zusammensetzen(zeilen: AsyncIterator[bytes]) -> dict[str, Any]:
    """SSE-Stücke im OpenAI-Format zu einer ganzen Antwort: Inhalt, Denken, Werkzeugaufrufe, Ende, Verbrauch."""
    kopf: dict[str, Any] = {}
    inhalt, denken, aufrufe, ende, verbrauch = [], [], {}, None, None
    async for zeile in zeilen:
        if not zeile.startswith(b"data: ") or zeile == b"data: [DONE]":
            continue
        try:
            teil = json.loads(zeile[6:])
        except ValueError:
            continue
        for feld in ("id", "created", "model"):
            kopf.setdefault(feld, teil.get(feld))
        verbrauch = teil.get("usage") or verbrauch
        for wahl in teil.get("choices") or []:
            delta = wahl.get("delta") or {}
            inhalt.append(delta.get("content") or "")
            denken.append(delta.get("reasoning_content") or delta.get("reasoning") or "")
            for t in delta.get("tool_calls") or []:
                a = aufrufe.setdefault(t.get("index", 0), {"id": None, "type": "function", "function": {"name": "", "arguments": ""}})
                a["id"] = t.get("id") or a["id"]
                f = t.get("function") or {}
                a["function"]["name"] += f.get("name") or ""
                a["function"]["arguments"] += f.get("arguments") or ""
            ende = wahl.get("finish_reason") or ende
    nachricht: dict[str, Any] = {"role": "assistant", "content": "".join(inhalt)}
    if "".join(denken):
        nachricht["reasoning_content"] = "".join(denken)
    if aufrufe:
        nachricht["tool_calls"] = [aufrufe[i] for i in sorted(aufrufe)]
    return {**kopf, "object": "chat.completion", "choices": [{"index": 0, "message": nachricht, "finish_reason": ende}],
            **({"usage": verbrauch} if verbrauch else {})}


class ExternOpenAI(OpenAIKompatibel):
    """Externer Anbieter im OpenAI-Format (zuerst Hetzner): nur `/v1/models`, nie Laden oder Entladen; mehrere Namen
    mit gleichem `root` sind ein Modell (Hetzner nennt jedes Modell zweimal). Jede Anfrage zählt für die Grenze je
    Minute, auch die Zustandsabfrage; die Leitstelle fragt deshalb selten (ZUSAMMENSPIEL Z4)."""

    async def zustand(self) -> Dienstbericht:
        try:
            r = await self._client.get("/v1/models", timeout=self._kurz)
            if r.status_code != 200:
                return Dienstbericht(erreichbar=False, meldung=f"Antwort {r.status_code}: {_fehlertext(r.content)}")
            daten = r.json().get("data", [])
        except (httpx.HTTPError, ValueError, AttributeError) as fehler:
            return Dienstbericht(erreichbar=False, meldung=f"nicht erreichbar: {type(fehler).__name__} {fehler}".strip())
        gruppen: dict[str, list[dict[str, Any]]] = {}
        for m in daten:
            gruppen.setdefault(str(m.get("root") or m["id"]), []).append(m)
        modelle = []
        for namen in gruppen.values():
            # Hauptname: mit Anbieter vorn, sonst der kürzeste; die übrigen sind Aliasse (Instanzen tragen alle Namen)
            namen = sorted(namen, key=lambda m: ("/" not in str(m["id"]), len(str(m["id"])), str(m["id"])))
            haupt = str(namen[0]["id"])
            einbettung = "embed" in haupt.lower()
            modelle.append(ModellBericht(schluessel=haupt, name=haupt.split("/")[-1], gb=0.0, geladen=True, einbettung=einbettung,
                                         faehigkeiten={F.EINBETTUNG} if einbettung else set(TEXT_FAEHIGKEITEN),
                                         instanzen=[str(m["id"]) for m in namen], parameter_mrd=_milliarden_im_namen(haupt),
                                         kontext=namen[0].get("max_model_len")))
        return Dienstbericht(erreichbar=True, steuerbar=False, modelle=modelle, meldung="externer Anbieter: immer bereit, Laden übernimmt der Anbieter")

    async def anfrage(self, pfad: str, koerper: dict[str, Any]) -> HttpStrom | GesammelteAntwort:
        """Immer als Strom zum Anbieter: Vorschaltrechner externer Anbieter brechen stille Anfragen nach einer Frist ab
        (Hetzner: 504 nach 300 s, gemessen 18.10.2026 an einem denkenden Modell); im Strom fließen die Token laufend.
        Wollte die Anwendung keinen Strom, setzt der Adapter die Antwort zusammen."""
        if koerper.get("stream") or not pfad.rstrip("/").endswith("chat/completions"):
            return await super().anfrage(pfad, koerper)
        strom = await super().anfrage(pfad, {**koerper, "stream": True, "stream_options": {"include_usage": True}})
        if strom.status >= 400:
            return strom
        try:
            antwort = await strom_zusammensetzen(strom.zeilen())
        finally:
            await strom.schliessen()
        return GesammelteAntwort(json.dumps(antwort, ensure_ascii=False).encode())

    async def laden(self, schluessel: str) -> str:
        raise DienstFehler("nicht_steuerbar", "Ein externer Anbieter lädt seine Modelle selbst.")

    async def entladen(self, instanz: str) -> None:
        raise DienstFehler("nicht_steuerbar", "Ein externer Anbieter entlädt seine Modelle selbst.")
