"""HELF-166, Entscheidung des Nutzers "ein Weg je Rechner": der Modell-Läufer eines Rechners geht über die Durchleitung
seines Maschinenraums (Adresse laeufer://<knoten>), mit dessen Schlüssel und über TLS, wenn er das meldet."""

from __future__ import annotations

import httpx
import pytest

from leitstelle.fach.fehler import Ablehnung
from leitstelle.fach.verzeichnis import _adresse_pruefen
from leitstelle.ports.ablage.eintraege import Adapterart
from leitstelle.ports.agenten import Agentenvermittlung
from leitstelle.ports.dienste import adapter_fabrik, laeufer_adresse
from leitstelle.protokoll.knoten import KnotenAnmeldung


def _anmeldung(tls: bool) -> KnotenAnmeldung:
    return KnotenAnmeldung(name="mac", betriebssystem="Darwin", architektur="arm64", speicher_gb=128, agent_version="t",
                           durchleitung_port=8541, durchleitung_tls=tls)


async def _senden(_nachricht) -> None:
    return None


def test_durchleitung_ueber_tls_wenn_gemeldet() -> None:
    agenten = Agentenvermittlung()
    v = agenten.anmelden("k1", _anmeldung(True), _senden, 0.0, adresse="192.168.1.45", schluessel="geheim")
    assert str(v.durchleitung) == "https://192.168.1.45:8541"
    v = agenten.anmelden("k1", _anmeldung(False), _senden, 0.0, adresse="192.168.1.45", schluessel="geheim")
    assert str(v.durchleitung) == "http://192.168.1.45:8541", "ein älterer Maschinenraum ohne TLS geht weiter"


async def test_laeufer_geht_ueber_die_durchleitung_mit_dem_schluessel_des_maschinenraums() -> None:
    gesehen: list[httpx.Request] = []

    def antwort(r: httpx.Request) -> httpx.Response:
        gesehen.append(r)
        return httpx.Response(200, json={"models": []})

    agenten = Agentenvermittlung()
    agenten.anmelden("k1", _anmeldung(True), _senden, 0.0, adresse="192.168.1.45", schluessel="geheim")
    bauen = adapter_fabrik(transport=httpx.MockTransport(antwort), agenten=agenten)
    adapter = bauen(Adapterart.OPENAI_KOMPATIBEL, laeufer_adresse("k1"), "eigener-zugang")
    try:
        bericht = await adapter.zustand()
    finally:
        await adapter.schliessen()
    assert bericht.erreichbar
    r = gesehen[0]
    assert str(r.url) == "https://192.168.1.45:8541/_laeufer/api/v1/models"
    assert r.headers["authorization"] == "Bearer geheim" and r.headers["host"] == "192.168.1.45:8541"


async def test_laeufer_ohne_verbundenen_maschinenraum_ist_nicht_erreichbar() -> None:
    bauen = adapter_fabrik(transport=httpx.MockTransport(lambda r: httpx.Response(200)), agenten=Agentenvermittlung())
    adapter = bauen(Adapterart.OPENAI_KOMPATIBEL, laeufer_adresse("fehlt"), None)
    try:
        assert not (await adapter.zustand()).erreichbar
    finally:
        await adapter.schliessen()


def test_adresse_laeufer_nur_im_heimnetz_und_mit_knoten() -> None:
    assert _adresse_pruefen("laeufer://k1/", extern=False) == "laeufer://k1"
    for adresse, extern in (("laeufer://", False), ("laeufer://k1", True)):
        with pytest.raises(Ablehnung):
            _adresse_pruefen(adresse, extern)
