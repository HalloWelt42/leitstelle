#!/usr/bin/env python3
"""Übernimmt die Stilblöcke der Entwürfe (mockups/*.html) in frontend/src/stil/seiten.css.

Jede Regel bekommt das Präfix ihrer Seite (.seite-<name>), damit gleichnamige Bausteine verschiedener
Entwürfe sich nicht überschreiben. Die Entwürfe rechnen mit ihren eigenen Marken (--ls-* in mockups/stil.css);
die Oberfläche nutzt die Marken des Appkerns: beim Übernehmen werden die Namen übersetzt und Mischungen aus
RGB-Werten (rgba(var(--ls-x-rgb), a)) zu color-mix. Aufruf aus der Projektwurzel: python3 tools/seitenstile.py
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
 * verschiedener Entwürfe sich nicht überschreiben. Erzeugt mit tools/seitenstile.py, mit den Marken des Appkerns
 * statt denen der Entwürfe; Änderungen an der Optik zuerst im Entwurf, dann neu erzeugen.
 */
"""


# Marken der Entwürfe -> Marken des Appkerns (oberflaeche/stil/marken.css im Appkern)
MARKEN = {
    "--ls-schrift-zahl": "--schrift-zahl", "--ls-schrift-code": "--schrift-code", "--ls-schrift": "--schrift",
    "--ls-gr-seite": "--seitentitel", "--ls-gr-titel": "--titel", "--ls-gr-text": "--gross", "--ls-gr-klein": "--klein",
    "--ls-gr-marke": "--marke", "--ls-gr-kennzahl": "--kennzahl", "--ls-ecke-klein": "--r1", "--ls-ecke": "--r2",
    "--ls-kopf-hoehe": "--kopf-hoehe", "--ls-seite-breite": "--nav-breite", "--ls-fuss-hoehe": "--fuss-hoehe",
    "--ls-schnell": "--schnell", "--ls-ruhig": "--ruhig", "--ls-grund": "--hg", "--ls-leiste": "--leiste",
    "--ls-flaeche": "--bereich", "--ls-karte-2": "--karte-2", "--ls-karte-3": "--karte-3", "--ls-karte": "--karte",
    "--ls-mulde": "--mulde", "--ls-text-2": "--text-2", "--ls-text-3": "--text-3", "--ls-text": "--text",
    "--ls-akzent-schrift": "--akzent", "--ls-akzent-text": "--auf-akzent", "--ls-akzent": "--akzent-flaeche",
    "--ls-erfolg": "--gut", "--ls-warnung": "--warn", "--ls-gefahr": "--gefahr", "--ls-info": "--info",
    "--ls-rand-stark": "--rand-stark", "--ls-rand": "--rand", "--ls-schleier": "--schleier",
    "--ls-schatten": "--schatten-schwebend", "--ls-diagrammlinie": "--diagrammlinie", "--ls-tint": "--toenung",
    **{f"--ls-a{i}": f"--a{i}" for i in range(1, 8)},
    **{f"--ls-{f}": f"--{f}" for f in ("himmel", "petrol", "tuerkis", "minze", "flieder", "violett", "rose", "koralle",
                                        "honig", "sand", "stahl")},
}


def marken_des_appkerns(css: str) -> str:
    """Marken der Entwürfe in die des Appkerns übersetzen; RGB-Mischungen werden color-mix."""
    def ziel(name: str) -> str:
        return MARKEN.get(name, name.replace("--ls-", "--"))
    css = re.sub(r"rgba\(var\((--[\w-]+?)-rgb\),\s*var\(--ls-tint\)\)",
                 lambda m: f"color-mix(in srgb, var({ziel(m.group(1))}) var(--toenung), transparent)", css)
    css = re.sub(r"rgba\(var\((--[\w-]+?)-rgb\),\s*([\d.]+)\)",
                 lambda m: f"color-mix(in srgb, var({ziel(m.group(1))}) {float(m.group(2)) * 100:g}%, transparent)", css)
    css = re.sub(r";\s*--[\w-]+-rgb:\s*var\(--ls-[\w-]+-rgb\);", ";", css)
    for alt in sorted(MARKEN, key=len, reverse=True):
        css = re.sub(re.escape(alt) + r"(?![\w-])", MARKEN[alt], css)
    css = re.sub(r"color: #fff\b", "color: var(--auf-farbe)", css)
    rest = sorted(set(re.findall(r"--ls-[\w-]+", css)))
    if rest:
        raise SystemExit(f"Marken der Entwürfe ohne Gegenstück im Appkern: {', '.join(rest)}")
    return css


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
            teile.append(f"\n/* ═══ {datei}.html ═══ */\n" + marken_des_appkerns(praefix(css, seite)).strip() + "\n")
    ziel = WURZEL / "frontend" / "src" / "stil" / "seiten.css"
    ziel.write_text("".join(teile), encoding="utf-8")
    print(f"{ziel.relative_to(WURZEL)}: {len(ziel.read_text(encoding='utf-8').splitlines())} Zeilen")


if __name__ == "__main__":
    main()
