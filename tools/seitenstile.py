#!/usr/bin/env python3
"""Übernimmt die Stilblöcke der Entwürfe (mockups/*.html) in frontend/src/stil/seiten.css.

Jede Regel bekommt das Präfix ihrer Seite (.seite-<name>), damit gleichnamige Bausteine verschiedener
Entwürfe sich nicht überschreiben. Aufruf aus der Projektwurzel: python3 tools/seitenstile.py
"""

import pathlib
import re

WURZEL = pathlib.Path(__file__).resolve().parents[1]
M = WURZEL / "mockups"
SEITEN = [("uebersicht", "uebersicht"), ("auftraege", "auftraege"), ("auftrag-stoppen", "auftraege"), ("modelle", "modelle"), ("knoten", "knoten"),
          ("dienste", "dienste"), ("anschluss-hinzufuegen", "anschluss"), ("anwendungen", "anwendungen"), ("anwendung-detail", "anwendungen"),
          ("protokoll", "protokoll"), ("mobil", "mobil")]
KOPF = """/*
 * Seitenstile der Oberfläche, übernommen aus den Stilblöcken der Entwürfe (mockups/*.html).
 * Jede Regel trägt das Präfix ihrer Seite (.seite-<name>), damit gleichnamige Bausteine
 * verschiedener Entwürfe sich nicht überschreiben. Erzeugt mit tools/seitenstile.py;
 * Änderungen an der Optik zuerst im Entwurf, dann neu erzeugen.
 */
"""


def stil(datei: str) -> str:
    t = (M / f"{datei}.html").read_text(encoding="utf-8")
    m = re.search(r"<style>(.*?)</style>", t, re.S)
    return m.group(1) if m else ""


def praefix(css: str, seite: str) -> str:
    if "@" in re.sub(r"/\*.*?\*/", "", css, flags=re.S):
        raise SystemExit(f"@-Regel im Entwurf {seite}: bitte Präfix von Hand setzen")
    aus = []
    for teil in re.split(r"(/\*.*?\*/)", css, flags=re.S):
        if teil.startswith("/*"):
            aus.append(teil)
            continue

        def regel(m: re.Match) -> str:
            vorlauf = re.match(r"\s*", m.group(1)).group(0)
            neue = []
            for s in m.group(1).split(","):
                s = s.strip()
                # Regeln für den ganzen Seitenkörper gehören zum Vorführrahmen des Entwurfs, nicht zur Seite
                if s and not s.startswith((":root", "html", "body")):
                    neue.append(f".seite-{seite} {s}")
            return vorlauf + ", ".join(neue) + " {" + m.group(2) + "}" if neue else vorlauf

        aus.append(re.sub(r"([^{}]+)\{([^{}]*)\}", regel, teil))
    return "".join(aus)


def main() -> None:
    teile = [KOPF]
    for datei, seite in SEITEN:
        css = stil(datei)
        if css.strip():
            teile.append(f"\n/* ═══ {datei}.html ═══ */\n" + praefix(css, seite).strip() + "\n")
    ziel = WURZEL / "frontend" / "src" / "stil" / "seiten.css"
    ziel.write_text("".join(teile), encoding="utf-8")
    print(f"{ziel.relative_to(WURZEL)}: {len(ziel.read_text(encoding='utf-8').splitlines())} Zeilen")


if __name__ == "__main__":
    main()
