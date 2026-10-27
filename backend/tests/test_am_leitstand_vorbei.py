"""Am Leitstand vorbei: die Zugriffe auf Modelle eines Rechners, die nicht über die Leitstelle gehen (`knoten.fremde`),
und die Last des Läufers, der Apps, des Rechners und des Docker-Rechners (`knoten.last`, ZUSAMMENSPIEL Z6). Szenarien
U06 bis U09 und L20 bis L23 und L28 aus docs/SZENARIEN.md, mit Leitstelle, Schein-Läufer und Schein-Agent auf echten Ports.

Die Leitstelle ist die zentrale Steuerung und Überwachung; den Modell-Läufer spricht sie direkt an. Was an ihr vorbei
auf Modelle zugreift, soll sichtbar sein, und wo es nötig ist, greift sie ein.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx

from leitstelle.api.app import erstellen
from leitstelle.fach.umgehungen import Umgehungsbuch
from leitstelle.kern.modelle import Regelwerk
from leitstelle.kern.werte import Massnahmenart
from leitstelle.konfig import Konfig
from leitstelle.ports.ablage.datenbank import Datenbank
from leitstelle.ports.ablage.repositorien import Ablage
from leitstelle.protokoll.knoten import (AppsLast, AppTeil, Befehlsart, DockerContainer, DockerLast, Fremdart, Fremdzugriff, Fremdzugriffe,
                                         KnotenLast, Laeuferprozess, Laeuferrolle)

from schein.agent import ScheinAgent
from schein.laeufer import schein_laeufer
from schein.server import laufend

PROGRAMM = Fremdzugriff(art=Fremdart.LAEUFER, wer="uvicorn (pappagei)", pid=4242, befehl="python -m uvicorn app:app", ordner="~/Entwicklung/pappagei",
                        verbindungen=2)
SPEICHER = Fremdzugriff(art=Fremdart.SPEICHER, wer="bildwerk.py", pid=5151, befehl="python bildwerk.py", ordner="~/Entwicklung/bildwerk", gb=11.6)
VON_DER_LEITSTELLE = Fremdzugriff(art=Fremdart.LAEUFER, wer="192.168.178.49", verbindungen=1, vom_rechner_der_leitstelle=True)


# ── Ende zu Ende: Leitstelle, Schein-Läufer und Schein-Agent ─────────────────────────────────────────────────────────
@dataclass
class Aufbau:
    c: httpx.AsyncClient          # Verwaltung
    knoten: str
    dienst: str                   # der Modell-Läufer des Mac
    agent: ScheinAgent


@asynccontextmanager
async def aufbau(tmp_path, nachlauf_s: float = 0.0, regelwerk: Regelwerk | None = None):
    """Mac Studio mit Läufer und Maschinenraum. Ein Regelwerk liegt vor dem Start in der Ablage."""
    if regelwerk is not None:
        db = Datenbank(tmp_path / "leitstelle.sqlite")
        await db.oeffnen()
        await Ablage(db).einstellungen.regelwerk_speichern(regelwerk)
        await db.schliessen()
    konfig = Konfig(daten=tmp_path, oberflaeche=None, dienst_takt_s=0.3, hinweis_s=1.0, fremde_nachlauf_s=nachlauf_s)
    async with laufend(schein_laeufer()) as laeufer_url, laufend(erstellen(konfig)) as url, httpx.AsyncClient(base_url=url, timeout=30) as c:
        r = await c.post("/api/dienste", json={"adresse": laeufer_url, "neuer_knoten": {"name": "Mac Studio", "adresse": "127.0.0.1", "speicher_gb": 128}})
        assert r.status_code == 200, r.text
        dienst, knoten = r.json()["kennung"], r.json()["knoten"]
        schluessel = (await c.post(f"/api/knoten/{knoten}/agent/schluessel/neu")).json()["schluessel"]
        agent = ScheinAgent(url, schluessel)
        await agent.verbinden()
        try:
            yield Aufbau(c=c, knoten=knoten, dienst=dienst, agent=agent)
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


async def _fremde(a: Aufbau) -> dict:
    return next(k for k in (await _lage(a))["knoten"] if k["kennung"] == a.knoten)["fremde"]


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


async def test_u07_ohne_eingetragenen_laeufer_ist_der_rechner_der_leitstelle_ein_anderes_programm(tmp_path):
    """Die Leitstelle spricht den Läufer direkt an: eine Verbindung von ihrem Rechner ist sie selbst, solange sie dort einen
    Läufer eingetragen hat; ohne ist es ein anderes Programm auf ihrem Rechner und zählt als Umgehung."""
    async with aufbau(tmp_path) as a:
        await _gemeldet(a, Fremdzugriffe(zugriffe=[VON_DER_LEITSTELLE]))
        assert (await _fremde(a))["umgehungen"] == 0 and await _vorbei(a) == []
        assert (await a.c.delete(f"/api/dienste/{a.dienst}")).status_code < 300
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
        assert (await _last(a))["stufe_grund"] == "Last nicht mehr gemessen"


async def test_l28_apps_und_docker_rechner_im_lagebild(tmp_path):
    """Die Apps des Stellwerks und der Docker-Rechner, wie der Maschinenraum sie meldet, stehen beim Rechner im Lagebild:
    Apps je Teil mit Kernen und Speicher, Container mit der Anwendung, der sie gehören (Docker-Projekte), und die
    Docker-Last. Die Fremdlast steht ohne die Container da (die virtuelle Maschine zählt nicht doppelt)."""
    async with aufbau(tmp_path, regelwerk=_regeln()) as a:
        r = await a.c.post("/api/anwendungen", json={"name": "Zusage", "docker_projekte": ["zusage", " zusage ", ""]})
        assert r.status_code == 200, r.text
        zusage = r.json()["kennung"]
        anwendung = next(x for x in (await _lage(a))["anwendungen"] if x["kennung"] == zusage)
        assert anwendung["docker_projekte"] == ["zusage"]                                        # bereinigt: ohne Leere und Doppelte
        r = await a.c.post("/api/anwendungen", json={"name": "Falsch", "docker_projekte": ["zwei worte"]})
        assert r.status_code == 422 and "zwei worte" in r.text

        apps = AppsLast(teile=[AppTeil(app="befehlsdienst", app_name="Befehlsdienst", teil="dienst", name="Dienst", pids=[700], cpu_prozent=0.5, gb=0.05),
                               AppTeil(app="fundus", app_name="Fundus", teil="qdrant", name="Vektorspeicher", pids=[960, 962], cpu_prozent=40.0, gb=4.0)])
        docker = DockerLast(kerne=8, speicher_gb=16.0, container=[
            DockerContainer(name="orbit-datenbank-1", projekt="orbit", cpu_prozent=12.0, gb=0.4),
            DockerContainer(name="zusage-datenbank-1", projekt="zusage", cpu_prozent=200.0, gb=1.5)])
        await a.agent.last_melden(KnotenLast(kerne=10, laeufer=[HAUPT], fremd_prozent=40.0, apps=apps, docker=docker))

        async def gemeldet():
            return (await _last(a))["docker"] is not None
        await _warte_bis(gemeldet)
        s = await _last(a)
        assert s["apps"]["gemessen"] and s["apps"]["gb"] == 4.05
        assert [(t["app_name"], t["name"], t["cpu_prozent"]) for t in s["apps"]["teile"]] == [("Fundus", "Vektorspeicher", 40.0), ("Befehlsdienst", "Dienst", 0.5)]
        d = s["docker"]
        assert d["gemessen"] and d["kerne"] == 8 and d["speicher_gb"] == 16.0
        assert [(c["name"], c["anwendung"], c["hintergrund"]) for c in d["container"]] == [("zusage-datenbank-1", "Zusage", False), ("orbit-datenbank-1", None, False)]
        assert d["last_prozent"] == 26.5 and d["last_mittel_prozent"] == 26.5                    # (200 + 12) % von 8 Kernen
        assert s["fremd_prozent"] == 18.8                                                        # 40 % minus 21,2 Punkte Container auf 10 Kernen

        await a.agent.last_melden(KnotenLast(kerne=10, laeufer=[HAUPT], fremd_prozent=40.0,
                                             apps=AppsLast(gemessen=False, meldung="Stellwerk meldet keine Prozessnummern")))

        async def ohne_zuordnung():
            return (await _last(a))["apps"]["gemessen"] is False
        await _warte_bis(ohne_zuordnung)
        s = await _last(a)
        assert s["apps"]["teile"] == [] and s["apps"]["meldung"] == "Stellwerk meldet keine Prozessnummern" and s["docker"] is None
