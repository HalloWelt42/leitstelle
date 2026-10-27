"""Dienste bearbeiten: je Art nur, was wirkt. Der Dienst des Maschinenraums ("Dienste auf ...") hat die Adresse
`agent://<Rechner>`, die die Leitstelle selbst vergibt; Plätze und Zustand meldet der Maschinenraum. Ein Formular, das alle
Felder unverändert mitschickt, darf daran nicht scheitern (Fehler bis 0.23: "Die Adresse muss mit http:// oder https://
beginnen")."""

from __future__ import annotations

from test_schlaf import aufbau


async def _dienste(c) -> dict[str, dict]:
    return {d["art"]: d for d in (await c.get("/api/lage")).json()["dienste"]}


async def test_dienst_des_maschinenraums_nur_der_name(tmp_path):
    async with aufbau(tmp_path) as a:
        d = await _dienste(a.c)
        agent, laeufer = d["agent"], d["openai_kompatibel"]
        assert agent["adresse"] == f"agent://{a.knoten}" and agent["aenderbar"] == ["name"]
        assert {"adresse", "plaetze", "zugang", "einbettung_instanzen"} <= set(laeufer["aenderbar"])

        # das ganze Formular, wie die Oberfläche es schickt: Adresse und übrige Werte unverändert
        r = await a.c.patch(f"/api/dienste/{agent['kennung']}", json={
            "name": "Dienste auf MacBook M4 Max 128 GB", "adresse": agent["adresse"], "plaetze": agent["plaetze"], "zugang": None,
            "anfragen_je_minute": 0, "abgleich_s": None, "einbettung_instanzen": 1, "einbettung_spielraum_gb": 4})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Dienste auf MacBook M4 Max 128 GB" and r.json()["adresse"] == agent["adresse"]

        r = await a.c.patch(f"/api/dienste/{agent['kennung']}", json={"adresse": "http://127.0.0.1:9"})
        assert r.status_code == 422 and r.json()["grund"] == "adresse" and "vergibt die Leitstelle selbst" in r.json()["begruendung"]
        r = await a.c.patch(f"/api/dienste/{agent['kennung']}", json={"plaetze": 3, "anfragen_je_minute": 10})
        assert r.status_code == 422 and r.json()["grund"] == "nicht_aenderbar", r.text
        assert "die Plätze und die Grenze je Minute" in r.json()["begruendung"] and "nur der Name" in r.json()["begruendung"]
        assert (await _dienste(a.c))["agent"]["plaetze"] == agent["plaetze"]

        # Modell-Läufer: unveränderte Adresse zählt nicht als Änderung; das Prüfprotokoll nennt, was sich geändert hat
        r = await a.c.patch(f"/api/dienste/{laeufer['kennung']}", json={"name": "Läufer", "adresse": laeufer["adresse"] + "/", "plaetze": laeufer["plaetze"]})
        assert r.status_code == 200 and r.json()["adresse"] == laeufer["adresse"]
        pruef = [(e["was"], e["gegenstand"]) for e in (await a.c.get("/api/pruefprotokoll")).json()["eintraege"]]
        assert ("Dienst geändert: der Name", "Läufer") in pruef and ("Dienst geändert: der Name", "Dienste auf MacBook M4 Max 128 GB") in pruef
        r = await a.c.patch(f"/api/dienste/{laeufer['kennung']}", json={"adresse": "ftp://127.0.0.1"})
        assert r.status_code == 422 and r.json()["grund"] == "adresse"
