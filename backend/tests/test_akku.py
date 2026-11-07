"""Akku und Plattengröße eines Rechners (LS-11): der Maschinenraum meldet sie mit den Messwerten, das Lagebild trägt sie
unverändert zur Oberfläche; Rechner ohne Akku melden keinen."""

from __future__ import annotations

from leitstelle.kern.werte import Dienstzustand, Faehigkeit as F
from leitstelle.kern.zuteiler import kandidaten
from leitstelle.protokoll.knoten import Akku, Messwerte

from conftest import lade, welt_mit
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


def test_s75_akku_unter_30_sperrt_bis_35():
    """LS-17: unter 30 % keine neue Arbeit, auch am Netzteil; frei erst wieder ab 35 % (kein Hin und Her um 30 %)."""
    w = welt_mit()
    v = w.verbund
    assert v.akku_melden("mac-32", 31) is None and not v.knoten["mac-32"].akku_gesperrt
    assert v.akku_melden("mac-32", 29) is True
    assert v.akku_melden("mac-32", 33) is None and v.knoten["mac-32"].akku_gesperrt, "zwischen 30 und 35 bleibt gesperrt"
    assert v.akku_melden("mac-32", 35) is False
    assert v.akku_melden("mac-32", None) is None and not v.knoten["mac-32"].akku_gesperrt


def test_s76_gesperrter_akku_arbeit_geht_auf_den_anderen_mac():
    """Beide Macs haben GLM geladen, das MacBook ist für Bilder bevorzugt, aber sein Akku ist unter 30 %: der Auftrag geht
    auf den Mac Studio; auch Sprachausgabe ist gesperrt."""
    w = welt_mit()
    v = w.verbund
    v.dienste["laeufer-32"].zustand = Dienstzustand.BEREIT
    lade(w, "glm@128")
    lade(w, "glm@32")
    v.knoten["mac-32"].bevorzugt_fuer = {F.BILD_BESCHREIBEN}
    v.akku_melden("mac-32", 20)
    a = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=5, festes_modell="glm-4.6v")
    w.laufen(6)
    assert v.auftraege[a.kennung].knoten == "mac-128"
    gebremst: list[str] = []
    stimme = w.auftrag("rufzeichen", F.STIMME, laufzeit_s=5)
    v.modelle["xtts@128"].dienst = "hoerer-32"            # Stimme nur auf dem MacBook
    v.dienste["hoerer-32"].faehigkeiten.add(F.STIMME)
    assert not kandidaten(v, stimme, "xtts", False, gebremst) and "Akku 20 %" in gebremst[0]


async def test_akku_meldung_im_betrieb(tmp_path):
    """Der Maschinenraum meldet 25 %: die Leitstelle meldet die Sperre und zeigt sie beim Rechner; bei 40 % wieder frei."""
    async with aufbau(tmp_path) as a:
        for prozent, gesperrt in ((25, True), (40, False)):
            await a.agent._senden("knoten.messwerte", Messwerte(speicher_gesamt_gb=32.0, speicher_belegt_gb=12.0,
                                                                akku=Akku(prozent=prozent, netzteil=True, laedt=True)))

            async def da():
                return (await _knoten(a))["akku_gesperrt"] is gesperrt
            await _warte_bis(da)
        texte = [m["text"] for m in (await a.c.get("/api/lage")).json()["meldungen"]]
        assert any("Akku 25 %, unter 30 %: nimmt keine neue Arbeit an" in t for t in texte)
        assert any("Akku 40 %, wieder über 35 %: nimmt wieder Arbeit an" in t for t in texte)
