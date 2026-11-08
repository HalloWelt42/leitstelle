"""Einordnen (LS-26, PROTOKOLL 6.7): feste Möglichkeiten nach ihrer Wahrscheinlichkeit wählen. Szenarien E22 bis E26 aus
docs/SZENARIEN.md über die Fassade mit dem Schein-Läufer, der `logprobs` wie der echte Läufer liefert (höchstens 10
Alternativen, `max_tokens` 1 leer); dazu das Lesen der Antworten für sich."""

from __future__ import annotations

import json

import pytest

from leitstelle.fach.einordnen import buchstaben_lesen, gruppen, ja_lesen
from leitstelle.fach.fehler import Ablehnung

from test_ende_zu_ende import _warte_bis, _zustand, aufbau

MODELL = "qwen/qwen3-next-80b"


def _antwort(werte: dict[str, float] | None) -> bytes:
    import math
    if werte is None:
        return json.dumps({"choices": [{"message": {"content": "A"}, "logprobs": None}]}).encode()
    oben = [{"token": t, "logprob": math.log(p)} for t, p in werte.items()]
    return json.dumps({"choices": [{"message": {"content": oben[0]["token"]}, "logprobs": {"content": [{**oben[0], "top_logprobs": oben}]}}]}).encode()


def test_lesen_zaehlt_schreibvarianten_zusammen():
    p = buchstaben_lesen(_antwort({"B": 0.6, " B": 0.1, "A": 0.2, ":C": 0.1}), ["haushalt", "garten", "finanzen"])
    assert p == pytest.approx({"haushalt": 0.2, "garten": 0.7, "finanzen": 0.1})
    assert ja_lesen(_antwort({"ja": 0.6, "Ja": 0.2, "nein": 0.1, "Hmm": 0.1})) == pytest.approx(0.8 / 0.9)


def test_nein_als_wortanfang_und_kein_hochrechnen_eines_rests():
    """Gesehen am 80B (08.11.2026): "nein" kommt als erstes Token "ne"; ohne Erkennung wurde ein Rest von ja zu 100 %."""
    assert ja_lesen(_antwort({"ne": 0.97, "nej": 0.01, "ja": 0.0001})) == pytest.approx(0.0001 / 0.9801, abs=1e-6)
    assert ja_lesen(_antwort({"j": 0.9, "n": 0.1})) == pytest.approx(0.9)
    with pytest.raises(Ablehnung):
        ja_lesen(_antwort({"Vielleicht": 0.99, "ja": 0.01}))


def test_lesen_ohne_passende_antwort_oder_wahrscheinlichkeiten():
    with pytest.raises(Ablehnung) as a:
        buchstaben_lesen(_antwort({"Z": 1.0}), ["a", "b"])
    assert a.value.grund == "dienst_fehler" and "keiner der Möglichkeiten" in a.value.begruendung
    with pytest.raises(Ablehnung) as a:
        ja_lesen(_antwort(None))
    assert "keine Wahrscheinlichkeiten" in a.value.begruendung


def test_gruppen_gleich_gross():
    assert [len(g) for g in gruppen([str(i) for i in range(11)])] == [6, 5]
    assert [len(g) for g in gruppen([str(i) for i in range(25)])] == [9, 9, 7]
    assert [len(g) for g in gruppen([str(i) for i in range(10)])] == [10]


async def test_e22_auswahl_und_ja_nein_ueber_die_fassade(tmp_path):
    """Zwei Fragen, zwei Aufrufe mit gleichem Anfang (Text vorn), je ein Auftrag der Fähigkeit einordnen."""
    async with aufbau(tmp_path) as (c, anw, lage, _):
        r = await anw.post("/einordnen", json={"model": MODELL, "text": "Rechnung vom Gärtner", "fragen": {
            "bereich": {"frage": "Welcher Bereich?", "moeglichkeiten": {"garten": "Garten", "finanzen": "Finanzen", "haushalt": "Haushalt"}},
            "dringend": {"art": "ja_nein", "frage": "Ist es dringend?"}}})
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["antworten"]["bereich"]["wahl"] == "garten"
        assert sum(e["antworten"]["bereich"]["wahrscheinlichkeiten"].values()) == pytest.approx(1.0)
        assert e["antworten"]["dringend"] == {"wahl": "ja", "wahrscheinlichkeiten": {"ja": 0.9, "nein": 0.1}, "mittel": None, "runden": 1}
        assert e["anfragen"] == 2 and e["modell"] == "Qwen3 Next 80B"
        a, b = lage.anfragen[-2:]
        assert a["logprobs"] is True and a["top_logprobs"] == 10 and a["max_tokens"] == 2 and a["temperature"] == 0
        assert a["messages"][0] == b["messages"][0] and a["messages"][1]["content"].startswith("Text:\nRechnung vom Gärtner\n\nFrage:")
        assert "A: Garten\nB: Finanzen\nC: Haushalt" in a["messages"][1]["content"]
        auftrag = r.headers["x-leitstelle-auftrag"]
        await _warte_bis(lambda: _zustand(c, auftrag, "fertig"))
        assert (await c.get(f"/api/auftraege/{auftrag}")).json()["faehigkeit"] == "einordnen"


async def test_e23_mehr_als_zehn_moeglichkeiten_in_runden(tmp_path):
    """25 Möglichkeiten: drei Gruppen (9, 9, 7), dann die drei Sieger gegeneinander; vier Aufrufe, zwei Runden."""
    async with aufbau(tmp_path) as (c, anw, lage, _):
        moeglich = {f"k{i:02d}": f"Kategorie {i}" for i in range(25)}
        r = await anw.post("/einordnen", json={"model": MODELL, "text": "Bild", "fragen": {"kategorie": {"frage": "Welche?", "moeglichkeiten": moeglich}}})
        assert r.status_code == 200, r.text
        k = r.json()["antworten"]["kategorie"]
        assert r.json()["anfragen"] == 4 and k["runden"] == 2
        assert k["wahl"] == "k00" and set(k["wahrscheinlichkeiten"]) == {"k00", "k09", "k18"}, "die letzte Runde: die Sieger der Gruppen"
        assert "A: Kategorie 0\nB: Kategorie 9\nC: Kategorie 18" in lage.anfragen[-1]["messages"][1]["content"]


async def test_e24_mehrfach_und_stufe(tmp_path):
    async with aufbau(tmp_path) as (c, anw, lage, _):
        lage.wahrscheinlichkeiten = lambda k: ({"nein": 0.8, "ja": 0.2} if "Wald" in k["messages"][-1]["content"]
                                                else {"ja": 0.9, "nein": 0.1} if "ja oder nein" in k["messages"][-1]["content"]
                                                else {"A": 0.25, "B": 0.5, "C": 0.25})
        r = await anw.post("/einordnen", json={"model": MODELL, "text": "Ein Hund am Strand", "fragen": {
            "schlagworte": {"art": "mehrfach", "frage": "Was ist zu sehen?", "moeglichkeiten": {"hund": "Hund", "strand": "Strand", "wald": "Wald"}},
            "laune": {"art": "stufe", "frage": "Wie fröhlich?", "moeglichkeiten": {"wenig": "wenig", "mittel": "mittel", "sehr": "sehr"}}}})
        assert r.status_code == 200, r.text
        a = r.json()["antworten"]
        assert a["schlagworte"]["wahl"] == ["hund", "strand"] and a["schlagworte"]["wahrscheinlichkeiten"]["wald"] == 0.2
        assert a["laune"]["wahl"] == "mittel" and a["laune"]["mittel"] == 1.0
        assert "aufsteigender Reihenfolge" in lage.anfragen[-1]["messages"][1]["content"]
        assert r.json()["anfragen"] == 4


async def test_e25_recht_und_eingaben(tmp_path):
    """Ohne Recht `einordnen` abgelehnt; unpassende Fragen mit 400 und deutschem Satz, bevor etwas eingereiht wird."""
    async with aufbau(tmp_path) as (c, anw, lage, _):
        vorher = len(lage.anfragen)
        for fragen, satz in [({"x": {"art": "ja_nein", "frage": "?", "moeglichkeiten": {"a": "A"}}}, "keine Möglichkeiten"),
                             ({"x": {"frage": "?", "moeglichkeiten": {"a": "A"}}}, "Mindestens zwei"),
                             ({"x": {"art": "stufe", "frage": "?", "moeglichkeiten": {f"s{i}": str(i) for i in range(11)}}}, "Höchstens 10 Stufen"),
                             ({"X Y": {"art": "ja_nein", "frage": "?"}}, "Fragenschlüssel")]:
            r = await anw.post("/einordnen", json={"model": MODELL, "text": "t", "fragen": fragen})
            assert r.status_code == 400 and satz in r.json()["error"]["message"], r.text
        assert len(lage.anfragen) == vorher
        r = await c.post("/api/anwendungen", json={"name": "Nur Text", "faehigkeiten": ["text"]})
        schluessel = r.json()["schluessel"]
        r = await anw.post("/einordnen", json={"model": MODELL, "text": "t", "fragen": {"x": {"art": "ja_nein", "frage": "?"}}},
                           headers={"Authorization": f"Bearer {schluessel}"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "faehigkeit_nicht_erlaubt", r.text


async def test_e26_modell_ohne_passende_antwort(tmp_path):
    """Antwortet das Modell mit nichts Passendem, endet die Anfrage mit `dienst_fehler` und dem Grund, nie mit einer Wahl."""
    async with aufbau(tmp_path) as (c, anw, lage, _):
        lage.wahrscheinlichkeiten = lambda k: {"Vielleicht": 1.0}
        r = await anw.post("/einordnen", json={"model": MODELL, "text": "t", "fragen": {"x": {"art": "ja_nein", "frage": "?"}}})
        assert r.status_code == 502 and "keiner der Möglichkeiten" in r.json()["error"]["message"], r.text
