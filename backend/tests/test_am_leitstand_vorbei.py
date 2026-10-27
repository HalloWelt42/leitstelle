"""Am Leitstand vorbei: der Weg zum Modell-Läufer über den Maschinenraum seines Rechners und die Zugriffe, die nicht
über die Leitstelle gehen (`knoten.fremde`). Szenarien U01 bis U09 aus docs/SZENARIEN.md; mit dem echten Maschinenraum
als Durchleitung A12 in test_knoten_agent.py.

Grundsatz des Nutzers: alles KI nur über die Leitstelle; was daran vorbeigeht, soll sichtbar sein. Vorgabe zum Weg:
"fallback per hand muss IMMER möglich sein", also nie ein stiller Rückfall, aber der Schalter aus heißt sofort direkt.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import pytest

from leitstelle.api.app import erstellen
from leitstelle.fach.umgehungen import Umgehungsbuch
from leitstelle.kern.modelle import Regelwerk
from leitstelle.kern.werte import Massnahmenart
from leitstelle.konfig import Konfig
from leitstelle.ports.ablage.datenbank import Datenbank
from leitstelle.ports.ablage.repositorien import Ablage
from leitstelle.ports.ablage.eintraege import Adapterart
from leitstelle.ports.agenten import Agentenvermittlung
from leitstelle.ports.dienste import adapter_fabrik
from leitstelle.ports.dienste.laeuferweg import OHNE_MASCHINENRAUM, UeberMaschinenraum
from leitstelle.ports.dienste.openai_kompatibel import OpenAIKompatibel
from leitstelle.ports.dienste.schnittstelle import DienstFehler, Durchleitung
from leitstelle.protokoll.knoten import Befehlsart, Fremdart, Fremdzugriff, Fremdzugriffe, KnotenAnmeldung, KnotenLast, Laeuferprozess, Laeuferrolle

from schein.agent import ScheinAgent
from schein.laeufer import Lage, schein_laeufer
from schein.server import laufend

MS_SCHLUESSEL = "ms_schluessel_nur_fuer_den_test"
MODELL = "qwen/qwen3-next-80b"
FRAGE = {"model": MODELL, "messages": [{"role": "user", "content": "hallo"}]}

PROGRAMM = Fremdzugriff(art=Fremdart.LAEUFER, wer="uvicorn (pappagei)", pid=4242, befehl="python -m uvicorn app:app", ordner="~/Entwicklung/pappagei",
                        verbindungen=2)
SPEICHER = Fremdzugriff(art=Fremdart.SPEICHER, wer="bildwerk.py", pid=5151, befehl="python bildwerk.py", ordner="~/Entwicklung/bildwerk", gb=11.6)
VON_DER_LEITSTELLE = Fremdzugriff(art=Fremdart.LAEUFER, wer="192.168.178.49", verbindungen=1, vom_rechner_der_leitstelle=True)


def _vermittlung(durchleitung_port: int | None = 4711) -> Agentenvermittlung:
    """Ein verbundener Maschinenraum auf "mac", so wie der Kanal ihn anmeldet."""
    async def senden(_u) -> None:
        return None
    a = Agentenvermittlung()
    a.anmelden("mac", KnotenAnmeldung(name="Mac Studio", betriebssystem="macOS", architektur="arm64", speicher_gb=64, agent_version="0.14.0",
                                      durchleitung_port=durchleitung_port), senden, 0.0, adresse="192.168.178.45", schluessel=MS_SCHLUESSEL)
    return a


def _mitschnitt() -> tuple[httpx.MockTransport, list[httpx.Request]]:
    gesehen: list[httpx.Request] = []

    def antworten(anfrage: httpx.Request) -> httpx.Response:
        gesehen.append(anfrage)
        return httpx.Response(200, json={"models": []} if anfrage.url.path.endswith("/models") else {"ok": True})
    return httpx.MockTransport(antworten), gesehen


async def test_u01_anfrage_landet_mit_dem_schluessel_des_maschinenraums_unter_laeufer():
    innen, gesehen = _mitschnitt()
    adapter = OpenAIKompatibel("http://192.168.178.45:1234/v1", zugang=None, transport=UeberMaschinenraum("mac", _vermittlung(), innen=innen))
    try:
        bericht = await adapter.zustand()
        strom = await adapter.anfrage("/v1/chat/completions", FRAGE)
        await strom.schliessen()
        strom = await adapter.durchleiten("", Durchleitung(methode="GET", pfad="api/v1/models", abfrage="a=1&b=%C3%A4"))
        await strom.schliessen()
    finally:
        await adapter.schliessen()
    assert bericht.erreichbar
    assert [str(a.url) for a in gesehen] == ["http://192.168.178.45:4711/laeufer/api/v1/models", "http://192.168.178.45:4711/laeufer/v1/chat/completions",
                                             "http://192.168.178.45:4711/laeufer/api/v1/models?a=1&b=%C3%A4"]
    assert all(a.headers["authorization"] == f"Bearer {MS_SCHLUESSEL}" and a.headers["host"] == "192.168.178.45:4711" for a in gesehen)
    assert json.loads(gesehen[1].content) == FRAGE                              # Körper unverändert


async def test_u02_ohne_maschinenraum_klare_meldung_und_kein_rueckfall():
    """Weder ohne Verbindung noch ohne gemeldete Durchleitung geht eine Anfrage an die eingetragene Adresse."""
    for vermittlung in (Agentenvermittlung(), _vermittlung(durchleitung_port=None)):
        innen, gesehen = _mitschnitt()
        adapter = OpenAIKompatibel("http://192.168.178.45:1234", transport=UeberMaschinenraum("mac", vermittlung, innen=innen))
        try:
            bericht = await adapter.zustand()
            with pytest.raises(DienstFehler) as f:
                await adapter.anfrage("/v1/chat/completions", FRAGE)
        finally:
            await adapter.schliessen()
        assert not bericht.erreichbar and bericht.meldung == OHNE_MASCHINENRAUM
        assert f.value.grund == "dienst_nicht_erreichbar" and f.value.meldung == OHNE_MASCHINENRAUM and f.value.wiederholbar
        assert gesehen == []


def test_u03_ueber_den_maschinenraum_geht_nur_der_laeufer():
    bauen = adapter_fabrik()
    for art, adresse in ((Adapterart.EXTERN_OPENAI, "https://anbieter.example/v1"), (Adapterart.AGENT, "agent://mac")):
        with pytest.raises(ValueError):
            bauen(art, adresse, None, maschinenraum="mac")


# ── Ende zu Ende: Leitstelle, Schein-Läufer und Schein-Agent (ohne Durchleitung) ───────────────────────────────────────
@dataclass
class Aufbau:
    c: httpx.AsyncClient          # Verwaltung
    anw: httpx.AsyncClient        # Anwendung (Fassade)
    knoten: str
    dienst: str                   # der Modell-Läufer des Mac
    agent: ScheinAgent
    laeufer: Lage


@asynccontextmanager
async def aufbau(tmp_path, nachlauf_s: float = 0.0, regelwerk: Regelwerk | None = None):
    """Mac Studio mit Läufer (direkter Weg) und Maschinenraum; eine Anwendung. Ein Regelwerk liegt vor dem Start in der Ablage."""
    if regelwerk is not None:
        db = Datenbank(tmp_path / "leitstelle.sqlite")
        await db.oeffnen()
        await Ablage(db).einstellungen.regelwerk_speichern(regelwerk)
        await db.schliessen()
    laeufer = schein_laeufer()
    konfig = Konfig(daten=tmp_path, oberflaeche=None, dienst_takt_s=0.3, hinweis_s=1.0, fremde_nachlauf_s=nachlauf_s)
    async with laufend(laeufer) as laeufer_url, laufend(erstellen(konfig)) as url, httpx.AsyncClient(base_url=url, timeout=30) as c:
        r = await c.post("/api/dienste", json={"adresse": laeufer_url, "neuer_knoten": {"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": 128}})
        assert r.status_code == 200, r.text
        dienst, knoten = r.json()["kennung"], r.json()["knoten"]
        schluessel = (await c.post(f"/api/knoten/{knoten}/agent/schluessel/neu")).json()["schluessel"]
        app_schluessel = (await c.post("/api/anwendungen", json={"name": "Codehilfe"})).json()["schluessel"]
        agent = ScheinAgent(url, schluessel)
        await agent.verbinden()
        async with httpx.AsyncClient(base_url=url, timeout=30, headers={"Authorization": f"Bearer {app_schluessel}"}) as anw:
            try:
                yield Aufbau(c=c, anw=anw, knoten=knoten, dienst=dienst, agent=agent, laeufer=laeufer.state.lage)
            finally:
                await agent.beenden()


async def _warte_bis(bedingung, sekunden: float = 10.0):
    for _ in range(int(sekunden * 20)):
        if await bedingung():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Bedingung nicht erreicht")


async def _lage(a: Aufbau) -> dict:
    return (await a.c.get("/api/lage")).json()


async def _laeufer(a: Aufbau) -> dict:
    return next(d for d in (await _lage(a))["dienste"] if d["kennung"] == a.dienst)


async def _fremde(a: Aufbau) -> dict:
    return next(k for k in (await _lage(a))["knoten"] if k["kennung"] == a.knoten)["fremde"]


async def _ist(a: Aufbau, zustand: str) -> bool:
    return (await _laeufer(a))["zustand"] == zustand


async def _vorbei(a: Aufbau) -> list[str]:
    """Meldungen zu Zugriffen am Leitstand vorbei, älteste zuerst."""
    return [m["text"] for m in reversed((await _lage(a))["meldungen"]) if m["text"].startswith("Am Leitstand vorbei")]


async def _gemeldet(a: Aufbau, f: Fremdzugriffe) -> None:
    """Meldung schicken und warten, bis die Leitstelle sie übernommen hat (Lagebild zeigt denselben Stand). Der Kanal
    arbeitet der Reihe nach: ist sie übernommen, sind es alle davor auch, wenn sie sich vom Stand davor unterscheidet."""
    await a.agent.fremde_melden(f)

    async def da():
        s = await _fremde(a)
        return s["beobachtet"] == f.beobachtet and [z["wer"] for z in s["zugriffe"]] == ([z.wer for z in f.zugriffe] if f.beobachtet else [])
    await _warte_bis(da)


async def test_u04_schalter_an_ohne_durchleitung_nicht_erreichbar_schalter_aus_sofort_direkt(tmp_path):
    async with aufbau(tmp_path) as a:
        await _warte_bis(lambda: _ist(a, "bereit"))
        r = await a.c.patch(f"/api/dienste/{a.dienst}", json={"ueber_maschinenraum": True})
        assert r.status_code == 200, r.text
        await _warte_bis(lambda: _ist(a, "nicht_erreichbar"))
        d = await _laeufer(a)
        assert d["ueber_maschinenraum"] and d["meldung"] == OHNE_MASCHINENRAUM and d["adresse"].startswith("http://127.0.0.1:")
        vorher = a.laeufer.aufrufe
        await asyncio.sleep(1.0)                                                  # mehrere Prüfungen
        r = await a.anw.post("/v1/chat/completions", json=FRAGE)
        assert r.status_code == 503 and r.json()["error"]["code"] == "dienst_nicht_erreichbar", r.text
        assert a.laeufer.aufrufe == vorher                                        # der direkte Weg bleibt zu
        assert any("Weg zum Läufer jetzt über den Maschinenraum" in m["text"] for m in (await _lage(a))["meldungen"])

        r = await a.c.patch(f"/api/dienste/{a.dienst}", json={"ueber_maschinenraum": False})
        assert r.status_code == 200 and not r.json()["ueber_maschinenraum"], r.text
        await _warte_bis(lambda: _ist(a, "bereit"))
        r = await a.anw.post("/v1/chat/completions", json=FRAGE)
        assert r.status_code == 200 and a.laeufer.aufrufe > vorher, r.text      # ohne Neueingabe der Adresse


async def test_u05_schalter_nur_fuer_den_laeufer_und_nur_ohne_zugang(tmp_path):
    async with aufbau(tmp_path) as a:
        r = await a.c.patch(f"/api/dienste/{a.dienst}", json={"ueber_maschinenraum": True, "zugang": "geheim"})
        assert r.status_code == 400 and r.json()["grund"] == "weg", r.text
        assert "kein Zugang" in r.json()["begruendung"]
        await a.c.patch(f"/api/dienste/{a.dienst}", json={"zugang": "geheim"})
        r = await a.c.patch(f"/api/dienste/{a.dienst}", json={"ueber_maschinenraum": True})
        assert r.status_code == 400 and r.json()["grund"] == "weg", r.text
        agentdienst = next(d for d in (await _lage(a))["dienste"] if d["art"] == "agent")
        r = await a.c.patch(f"/api/dienste/{agentdienst['kennung']}", json={"ueber_maschinenraum": True})
        assert r.status_code == 400 and r.json()["grund"] == "weg", r.text
        assert not (await _laeufer(a))["ueber_maschinenraum"]


async def test_u06_fremde_zugriffe_im_lagebild_mit_deutung_und_einmal_gemeldet(tmp_path):
    """Auf dem direkten Weg ist die Verbindung vom Rechner der Leitstelle vermutlich sie selbst: sichtbar, aber keine
    Umgehung und keine Meldung. Dieselbe Liste im nächsten Takt meldet nichts neu."""
    async with aufbau(tmp_path, nachlauf_s=60.0) as a:
        s = await _fremde(a)
        assert s == {"beobachtet": False, "zugriffe": [], "umgehungen": 0}       # bis zur ersten Meldung
        alle = Fremdzugriffe(zugriffe=[PROGRAMM, SPEICHER, VON_DER_LEITSTELLE])
        await _gemeldet(a, alle)
        s = await _fremde(a)
        assert s["beobachtet"] and s["umgehungen"] == 2
        assert [z["deutung"] for z in s["zugriffe"]] == ["umgehung", "umgehung", "leitstelle_direkt"]
        assert s["zugriffe"][0] | {"deutung": None} == PROGRAMM.model_dump(mode="json") | {"deutung": None}
        assert await _vorbei(a) == [
            "Am Leitstand vorbei auf Mac Studio: uvicorn (pappagei) (Prozess 4242, ~/Entwicklung/pappagei) spricht den Modell-Läufer direkt an",
            "Am Leitstand vorbei auf Mac Studio: bildwerk.py (Prozess 5151, ~/Entwicklung/bildwerk) belegt 11,6 GB außerhalb von Diensten und Läufer"]
        for _ in range(3):
            await a.agent.fremde_melden(alle)
        await a.agent.fremde_melden(Fremdzugriffe(zugriffe=[PROGRAMM]))          # kurz weg, im Nachlauf: kein Flackern
        await _gemeldet(a, Fremdzugriffe(zugriffe=[PROGRAMM, SPEICHER]))
        assert len(await _vorbei(a)) == 2


async def test_u07_ueber_den_maschinenraum_ist_der_rechner_der_leitstelle_ein_anderes_programm(tmp_path):
    async with aufbau(tmp_path) as a:
        await _gemeldet(a, Fremdzugriffe(zugriffe=[VON_DER_LEITSTELLE]))
        assert (await _fremde(a))["umgehungen"] == 0 and await _vorbei(a) == []
        assert (await a.c.patch(f"/api/dienste/{a.dienst}", json={"ueber_maschinenraum": True})).status_code == 200
        s = await _fremde(a)
        assert s["umgehungen"] == 1 and s["zugriffe"][0]["deutung"] == "rechner_der_leitstelle"   # sofort neu gedeutet
        await _gemeldet(a, Fremdzugriffe(zugriffe=[VON_DER_LEITSTELLE]))
        assert await _vorbei(a) == ["Am Leitstand vorbei auf Mac Studio: 192.168.178.49 (anderes Programm auf dem Rechner der Leitstelle) "
                                    "spricht den Modell-Läufer direkt an"]


async def test_u08_verschwunden_einmal_gemeldet_ohne_beobachtung_nichts(tmp_path):
    async with aufbau(tmp_path) as a:
        await _gemeldet(a, Fremdzugriffe(zugriffe=[PROGRAMM, SPEICHER]))
        await _gemeldet(a, Fremdzugriffe(beobachtet=False))                     # sagt nichts: weder weg noch da
        s = await _fremde(a)
        assert s == {"beobachtet": False, "zugriffe": [], "umgehungen": 0}
        assert len(await _vorbei(a)) == 2
        await _gemeldet(a, Fremdzugriffe(zugriffe=[SPEICHER]))
        await a.agent.fremde_melden(Fremdzugriffe())
        await a.agent.fremde_melden(Fremdzugriffe())
        await _gemeldet(a, Fremdzugriffe(zugriffe=[VON_DER_LEITSTELLE]))         # keine Umgehung auf dem direkten Weg
        assert (await _vorbei(a))[2:] == ["Am Leitstand vorbei auf Mac Studio: uvicorn (pappagei) (Prozess 4242) nicht mehr gesehen",
                                         "Am Leitstand vorbei auf Mac Studio: bildwerk.py (Prozess 5151) nicht mehr gesehen"]
        s = await _fremde(a)
        assert s["beobachtet"] and s["umgehungen"] == 0 and [z["deutung"] for z in s["zugriffe"]] == ["leitstelle_direkt"]


def test_u09_nachlauf_gegen_flackern():
    buch = Umgehungsbuch(nachlauf_s=60.0)
    assert buch.abgleichen("mac", [PROGRAMM], 0.0) == ([PROGRAMM], [])
    assert buch.abgleichen("mac", [], 30.0) == ([], [])                          # im Nachlauf: noch nicht weg
    assert buch.abgleichen("mac", [PROGRAMM], 45.0) == ([], [])                  # wieder da: nicht neu
    assert buch.abgleichen("mac", [], 104.0) == ([], [])
    assert buch.abgleichen("mac", [], 105.0) == ([], [PROGRAMM])                 # 60 s nach dem letzten Sehen
    assert buch.abgleichen("mac", [], 500.0) == ([], [])                         # einmal
    buch.abgleichen("mac", [PROGRAMM], 600.0)
    buch.vergessen("mac")                                                        # Maschinenraum getrennt
    assert buch.abgleichen("mac", [PROGRAMM], 610.0) == ([PROGRAMM], [])


# ── Last des Läufers und des Rechners (ZUSAMMENSPIEL Z6), mit dem Schein-Agenten ────────────────────────────────────────
DATEI = "~/.lmstudio/models/lmstudio-community/bge-m3-GGUF/bge-m3-Q8_0.gguf"
HAUPT = Laeuferprozess(pid=807, name="Läufer", rolle=Laeuferrolle.HAUPT, cpu_prozent=3.0, gb=0.6)
ARBEITER = Laeuferprozess(pid=808, name="node (Läufer)", rolle=Laeuferrolle.ARBEITER, modelldatei=DATEI, cpu_prozent=98.0, gb=1.2)


def _regeln(**mehr) -> Regelwerk:
    """Kurze Fristen für den Test: ohne Auftrag nach 1 s, Mittel der Fremdlast über 60 s."""
    return Regelwerk(umschichter_takt_s=0.2, laeufer_frist_s=1.0, **mehr)


async def _last(a: Aufbau) -> dict:
    return next(k for k in (await _lage(a))["knoten"] if k["kennung"] == a.knoten)["last"]


async def _verlauf(a: Aufbau, anfang: str) -> list[str]:
    return [m["text"] for m in reversed((await _lage(a))["meldungen"]) if m["text"].startswith(anfang)]


async def _ohne_auftrag_gemeldet(a: Aufbau, fremd: float = 20.0) -> None:
    """Zwei Meldungen mit mehr als der Frist dazwischen: der Arbeiter rechnet ohne Auftrag."""
    await a.agent.last_melden(KnotenLast(kerne=10, laeufer=[HAUPT, ARBEITER], fremd_prozent=fremd))
    await asyncio.sleep(1.3)
    await a.agent.last_melden(KnotenLast(kerne=10, laeufer=[HAUPT, ARBEITER], fremd_prozent=fremd))

    async def befund():
        return any(p["ohne_auftrag_seit_s"] is not None for p in (await _last(a))["laeufer"])
    await _warte_bis(befund)


async def test_l20_last_im_lagebild_befund_einmal_im_verlauf_und_von_hand_beenden(tmp_path):
    async with aufbau(tmp_path, regelwerk=_regeln()) as a:
        s = await _last(a)
        assert s["gemeldet"] is False and s["laeufer"] == [] and s["stufe"] == "frei"           # bis zur ersten Meldung
        await asyncio.sleep(1.1)                                                                 # die Modelle des Läufers gelten bei der Einrichtung als genutzt
        await _ohne_auftrag_gemeldet(a)
        s = await _last(a)
        assert s["gemeldet"] and s["gemessen"] and s["kerne"] == 10 and s["fremd_prozent"] == 20.0 and s["auftraege"] == 0
        assert [(p["pid"], p["rolle"], p["cpu_prozent"]) for p in s["laeufer"]] == [(807, "haupt", 3.0), (808, "arbeiter", 98.0)]
        assert s["laeufer"][0]["ohne_auftrag_seit_s"] is None and s["laeufer"][1]["modelldatei"] == DATEI
        await a.agent.last_melden(KnotenLast(kerne=10, laeufer=[HAUPT, ARBEITER], fremd_prozent=20.0))
        befunde = await _verlauf(a, "Läufer auf Mac Studio")
        assert len(befunde) == 1 and befunde[0].startswith("Läufer auf Mac Studio: node (Läufer) (Prozess 808, bge-m3-Q8_0.gguf) rechnet seit ")
        assert befunde[0].endswith("ohne Auftrag der Leitstelle mit 1,0 Kernen")
        assert a.agent.befehle == []                                                             # Regel ab Werk aus: nur Befund

        r = await a.c.post(f"/api/knoten/{a.knoten}/laeufer/807/beenden")
        assert r.status_code == 409 and "kein Arbeiter" in r.json()["begruendung"], r.text   # Hauptprozess nie
        r = await a.c.post(f"/api/knoten/{a.knoten}/laeufer/808/beenden")
        assert r.status_code == 200 and r.json()["erfolg"], r.text
        assert [(b.befehl, b.ziel) for b in a.agent.befehle] == [(Befehlsart.LAEUFER_PROZESS_BEENDEN, "808")]
        assert (await _last(a))["laeufer"][1]["beenden_s"] is not None
        assert "Läufer auf Mac Studio: Prozess 808 beendet: auf Bitte (SIGTERM)" in await _verlauf(a, "Läufer auf Mac Studio")
        r = await a.c.post(f"/api/knoten/{a.knoten}/laeufer/808/beenden")
        assert r.status_code == 409 and "schon beendet" in r.json()["begruendung"]
        await a.agent.last_melden(KnotenLast(kerne=10, laeufer=[HAUPT], fremd_prozent=20.0))   # der Läufer hat die Instanz entladen

        async def weg():
            return (await _verlauf(a, "Läufer auf Mac Studio"))[-1] == "Läufer auf Mac Studio: node (Läufer) (Prozess 808) ist beendet"
        await _warte_bis(weg)


async def test_l21_von_hand_erst_nach_der_frist(tmp_path):
    """Dieselbe Prüfung wie die Regel: gerade erst über der Schwelle (und die Modelle des Läufers eben noch genutzt) heißt
    nicht ohne Auftrag."""
    async with aufbau(tmp_path, regelwerk=_regeln()) as a:
        await a.agent.last_melden(KnotenLast(kerne=10, laeufer=[HAUPT, ARBEITER], fremd_prozent=20.0))

        async def da():
            return len((await _last(a))["laeufer"]) == 2
        await _warte_bis(da)
        r = await a.c.post(f"/api/knoten/{a.knoten}/laeufer/808/beenden")
        assert r.status_code == 409 and r.json()["begruendung"] == ("node (Läufer) (Prozess 808) wird nicht beendet: er rechnet nicht seit der "
                                                                     "Frist über der Schwelle ohne Auftrag."), r.text
        assert a.agent.befehle == []


async def test_l22_regel_an_beendet_selbst(tmp_path):
    regeln = _regeln()
    regeln.szenarien_an[Massnahmenart.LAEUFER_OHNE_AUFTRAG] = True
    async with aufbau(tmp_path, regelwerk=regeln) as a:
        await asyncio.sleep(1.1)
        await _ohne_auftrag_gemeldet(a)

        async def beendet():
            return [(b.befehl, b.ziel) for b in a.agent.befehle] == [(Befehlsart.LAEUFER_PROZESS_BEENDEN, "808")]
        await _warte_bis(beendet)
        assert any(m["grund"].startswith("Läufer auf Mac Studio: node (Läufer) mit bge-m3-Q8_0.gguf rechnete") for m in (await _lage(a))["massnahmen"])


async def test_l23_rechnerlast_haelt_hintergrund_an_und_gibt_ihn_frei(tmp_path):
    async with aufbau(tmp_path, regelwerk=_regeln(last_frist_s=60.0)) as a:
        for _ in range(3):
            await a.agent.last_melden(KnotenLast(kerne=10, laeufer=[HAUPT], fremd_prozent=90.0))

        async def stufe(wert: str):
            async def gleich():
                return (await _last(a))["stufe"] == wert
            return gleich
        await _warte_bis(await stufe("angehalten"))
        s = await _last(a)
        assert s["stufe_grund"] == "Fremdlast 90 %, anhalten ab 75 %" and s["fremd_mittel_prozent"] == 90.0
        assert "Hintergrund auf Mac Studio angehalten (vorher frei): Fremdlast im Mittel 90 %, anhalten ab 75 %" in await _verlauf(a, "Hintergrund")
        await a.agent.trennen()                                                                  # ohne Maschinenraum keine Messung: frei
        await _warte_bis(await stufe("frei"))
        assert (await _last(a))["stufe_grund"] == "Fremdlast nicht mehr gemessen"
