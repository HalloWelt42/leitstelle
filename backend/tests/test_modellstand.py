"""Modellstand der Maschinenraum-Dienste Ende zu Ende (LS-34, MR-7): echte Leitstelle auf einem Port, als Agent der
Maschinenraum mit einem Probedienst, dessen Modellprüfung eine Datei in seiner Wegwerf-Ablage sucht. Fehlt sie, ist der
Dienst für Apps ausgeblendet, eine Anfrage endet sofort, die Oberfläche nennt den Grund; kommt sie zurück, ist alles
ohne Eingriff wieder da."""

from __future__ import annotations

import sys
import time

import httpx

from test_knoten_agent import _agentenordner, _freier_port, _modell, _warte_bis, agent_laeuft, aufbau

PRUEFUNG = ("import os, sys; da = os.path.exists(os.path.join(os.environ['MASCHINENRAUM_MODELLE'], 'probe.bin')); "
            "print('vorhanden: Probe' if da else 'fehlt: probe.bin nicht in der Ablage'); sys.exit(0 if da else 1)")


async def test_ohne_modell_ausgeblendet_sofort_abgesagt_und_zurueck(tmp_path):
    port = _freier_port()
    (tmp_path / "hallo.txt").write_text("Grüße aus dem Dienst")
    async with aufbau(tmp_path) as (c, url, knoten, schluessel):
        app = (await c.post("/api/anwendungen", json={"name": "Sprache", "faehigkeiten": ["stimme"]})).json()["schluessel"]
        kopf = {"Authorization": f"Bearer {app}"}
        o = _agentenordner(tmp_path, url, schluessel, port, mehr=f'modellpruefung = ["{sys.executable}", "-c", "{PRUEFUNG}"]\n')
        o.modelle.mkdir(parents=True)
        async with agent_laeuft(o), httpx.AsyncClient(base_url=url, timeout=60) as anw:
            async def fehlt():
                m = await _modell(c, "probe")
                return m is not None and m.get("fehlt") == "probe.bin nicht in der Ablage"
            await _warte_bis(fehlt)

            modelle = (await anw.get("/v1/models", headers=kopf)).json()["data"]
            dienste = (await anw.get("/v1/dienste", headers=kopf)).json()["data"]
            assert "probe" not in [m["id"] for m in modelle] and "probe" not in [d["kennung"] for d in dienste]   # ausgeblendet

            beginn = time.monotonic()
            r = await anw.get("/v1/dienste/probe/hallo.txt", headers=kopf)
            assert r.status_code == 503 and r.json()["error"]["code"] == "modell_nicht_vorhanden", r.text
            assert "probe.bin nicht in der Ablage" in r.json()["error"]["message"] and time.monotonic() - beginn < 5

            (o.modelle / "probe.bin").write_bytes(b"x")                 # das Modell kommt zurück
            async def wieder_da():
                m = await _modell(c, "probe")
                return m is not None and m.get("fehlt") is None
            await _warte_bis(wieder_da)
            modelle = (await anw.get("/v1/models", headers=kopf)).json()["data"]
            assert "probe" in [m["id"] for m in modelle]
            r = await anw.get("/v1/dienste/probe/hallo.txt", headers=kopf)
            assert r.status_code == 200 and r.content.decode() == "Grüße aus dem Dienst"
