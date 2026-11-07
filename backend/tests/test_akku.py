"""Akku und Plattengröße eines Rechners (LS-11): der Maschinenraum meldet sie mit den Messwerten, das Lagebild trägt sie
unverändert zur Oberfläche; Rechner ohne Akku melden keinen."""

from __future__ import annotations

from leitstelle.protokoll.knoten import Akku, Messwerte

from test_schlaf import _knoten, _warte_bis, aufbau


async def test_akku_und_platte_kommen_im_lagebild_an(tmp_path):
    async with aufbau(tmp_path) as a:
        akku = Akku(prozent=47, netzteil=True, laedt=True, rest_min=182, kapazitaet_prozent=96.0, zyklen=41)
        await a.agent._senden("knoten.messwerte", Messwerte(speicher_gesamt_gb=32.0, speicher_belegt_gb=12.0, platte_frei_gb=814.9,
                                                            platte_gesamt_gb=926.4, akku=akku))

        async def angekommen():
            return ((await _knoten(a))["agent"].get("messwerte") or {}).get("akku") is not None
        await _warte_bis(angekommen)
        mw = (await _knoten(a))["agent"]["messwerte"]
        assert mw["akku"] == akku.model_dump(mode="json") and mw["platte_gesamt_gb"] == 926.4

        await a.agent._senden("knoten.messwerte", Messwerte(speicher_gesamt_gb=128.0, speicher_belegt_gb=40.0))

        async def ohne():
            return (await _knoten(a))["agent"]["messwerte"]["speicher_gesamt_gb"] == 128.0
        await _warte_bis(ohne)
        assert (await _knoten(a))["agent"]["messwerte"]["akku"] is None
