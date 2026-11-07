"""Akku und Plattengröße eines Rechners (LS-11): der Maschinenraum meldet sie mit den Messwerten, das Lagebild trägt sie
unverändert zur Oberfläche; Rechner ohne Akku melden keinen."""

from __future__ import annotations

from leitstelle.kern.werte import Dienstzustand, Faehigkeit as F
from leitstelle.kern.zuteiler import kandidaten
from leitstelle.protokoll.knoten import Akku, Messwerte

from conftest import ausgefuehrt, lade, welt_mit
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


def test_s84_gesperrter_akku_ist_kein_ziel_der_selbststeuerung():
    """Der Fall aus S07 (Bildauftrag wartet am Mac Studio, das MacBook hätte Platz), aber der Akku des MacBooks ist unter
    30 %: die Leitstelle leitet nicht um, startet dort keinen Dienst und lädt dort kein Modell (LS-22, 07.11.2026: das
    MacBook rechnete bei 7 % weiter)."""
    from leitstelle.kern.werte import Auftragszustand as Z, Massnahmenart as A, Modellzustand
    w = welt_mit()
    v = w.verbund
    v.akku_melden("mac-32", 20)
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    k = w.auftrag("kiste", F.BILD_BESCHREIBEN, laufzeit_s=8)
    w.laufen(60)
    assert not ausgefuehrt(w, A.UMLEITEN)
    assert v.dienste["laeufer-32"].zustand != Dienstzustand.BEREIT, "kein Dienststart auf dem gesperrten Mac"
    assert all(not m.im_speicher for m in v.modelle_auf("mac-32") if m.dienst == "laeufer-32")
    assert v.auftraege[k.kennung].zustand != Z.FERTIG or v.auftraege[k.kennung].knoten == "mac-128"
    v.akku_melden("mac-32", 70)
    w.laufen_bis_fertig(200)
    assert v.auftraege[k.kennung].zustand == Z.FERTIG
    assert not [m for m in v.modelle.values() if m.zustand == Modellzustand.LAEDT]


def test_s85_einbettung_wird_auf_gesperrtem_mac_nicht_verstaerkt():
    """Einbettung wartet auf dem MacBook mit gesperrtem Akku: keine weitere Instanz dort."""
    from leitstelle.kern.regeln.bausteine import Kontext, einbettungsinstanzen_moeglich
    w = welt_mit()
    v = w.verbund
    v.akku_melden("mac-32", 10)
    k = Kontext(verbund=v, messwerk=w.messwerk, instanz="bge-m3@mac-32", knoten_quelle="mac-32",
                werte={"familie": "bge-m3", "wartende": 3, "auftraege": []})
    assert einbettungsinstanzen_moeglich(k) is False and "Akku gesperrt" in k.werte["instanz"]
