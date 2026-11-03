#!/usr/bin/env python3
"""Zugang einer Anwendung in der Leitstelle anlegen, ohne den Schlüssel anzuzeigen: er geht nur in eine Datei mit den
Rechten 600 (wie app_zugang der Kellerwolke). Gibt es die Anwendung schon, wird ihr Schlüssel übernommen; fehlende
Fähigkeiten kommen dazu, weggenommen wird nichts. Spricht die Verwaltung der Leitstelle an (nur aus dem Heimnetz).

    python3 tools/anwendung_zugang.py --name Helfer-Probe --faehigkeiten musik --datei ~/.config/leitstelle/helfer-probe.schluessel
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

VORGABE_ADRESSE = "http://192.168.178.49:8530"


def anfrage(adresse: str, methode: str, pfad: str, daten: dict | None = None) -> dict:
    koerper = json.dumps(daten).encode() if daten is not None else None
    r = urllib.request.Request(f"{adresse}{pfad}", data=koerper, method=methode, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as antwort:
        return json.load(antwort)


def main() -> int:
    teiler = argparse.ArgumentParser(description="Zugang einer Anwendung in der Leitstelle, Schlüssel nur in eine Datei")
    teiler.add_argument("--name", required=True)
    teiler.add_argument("--faehigkeiten", required=True, help="durch Komma getrennt, etwa musik oder text,einbettung")
    teiler.add_argument("--datei", required=True, type=Path)
    teiler.add_argument("--adresse", default=os.environ.get("LEITSTELLE_ADRESSE", VORGABE_ADRESSE))
    a = teiler.parse_args()
    erklaert = sorted({f.strip() for f in a.faehigkeiten.split(",") if f.strip()})
    anwendungen = anfrage(a.adresse, "GET", "/api/lage").get("anwendungen", [])
    vorhanden = next((x for x in anwendungen if x["name"].lower() == a.name.lower()), None)
    if vorhanden is None:
        schluessel = anfrage(a.adresse, "POST", "/api/anwendungen", {"name": a.name, "faehigkeiten": erklaert})["schluessel"]
        was = f"angelegt ({', '.join(erklaert)})"
    else:
        fehlen = set(erklaert) - set(vorhanden["faehigkeiten"])
        if fehlen:
            daten = {k: vorhanden[k] for k in ("name", "prioritaet", "zonen", "extern_erlaubt", "gleichzeitig", "ketten", "docker_projekte")}
            anfrage(a.adresse, "PUT", f"/api/anwendungen/{vorhanden['kennung']}",
                    {**daten, "faehigkeiten": sorted(set(vorhanden["faehigkeiten"]) | fehlen)})
        schluessel = anfrage(a.adresse, "POST", f"/api/anwendungen/{vorhanden['kennung']}/schluessel")["schluessel"]
        was = "vorhanden, Schlüssel übernommen" + (f", Fähigkeiten dazu: {', '.join(sorted(fehlen))}" if fehlen else "")
    datei = a.datei.expanduser()
    datei.parent.mkdir(parents=True, exist_ok=True)
    alt = os.umask(0o077)
    try:
        datei.write_text(schluessel + "\n", encoding="utf-8")
    finally:
        os.umask(alt)
    os.chmod(datei, 0o600)
    print(f"Leitstelle: {a.name} {was}; Schlüssel in {datei} (600)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
