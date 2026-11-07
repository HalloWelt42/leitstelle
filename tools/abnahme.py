"""Abnahme der Arbeitslogik im Betrieb (LS-20): echte Aufträge gegen die laufende Leitstelle, jedes erwartete Verhalten
geprüft, Bericht als Markdown (und auf Wunsch als Kommentar ans Ticket).

    backend/.venv/bin/python tools/abnahme.py [--haus privat/abnahme.toml] [--nur L1,L3] [--bericht-ans-ticket]

Ablauf: Warteschlangen der Apps anhalten, Prüffenster öffnen (nur die Anwendung der Abnahme bekommt neue Arbeit,
Sprachausgabe läuft weiter), auf das Ende laufender Live-Arbeit warten, Szenarien L1 bis L7, danach in jedem Fall
Probewerte zurück, Fenster zu, Warteschlangen fortsetzen. Adressen, Modelle und Befehle des Hauses stehen in der Datei
des Hauses (privat), der Schlüssel nur am Mac; hier steht nichts davon.
"""

from __future__ import annotations

import argparse
import json
import ssl
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

WURZEL = Path(__file__).resolve().parent.parent
TICKET = Path.home() / ".config" / "pinnwand" / "ticket.py"
TITEL = "Abnahme LS-20 geheim"              # darf in keiner Auskunft auftauchen


# ── Datei des Hauses ─────────────────────────────────────────────────────

@dataclass
class Warteschlange:
    name: str
    anhalten: str
    fortsetzen: str
    zustand_weiterreichen: bool = False
    stand: str | None = None
    angehalten_wenn: str | None = None
    vorher: str = ""                         # Ausgabe von "anhalten" (Zustand davor)
    angefasst: bool = False


@dataclass
class Haus:
    leitstelle: str
    schluessel: str
    dauer_s: float
    ticket: str
    rechner: dict[str, str]
    modelle: dict[str, str]
    fristen: dict[str, float]
    warteschlangen: list[Warteschlange]

    @classmethod
    def laden(cls, pfad: Path) -> Haus:
        d = tomllib.loads(pfad.read_text(encoding="utf-8"))
        schluessel = Path(d["schluessel_datei"]).expanduser().read_text(encoding="utf-8").strip()
        return cls(leitstelle=d["leitstelle"].rstrip("/"), schluessel=schluessel, dauer_s=float(d["dauer_s"]), ticket=d["ticket"],
                   rechner=d["rechner"], modelle=d["modelle"], fristen={k: float(v) for k, v in d["fristen"].items()},
                   warteschlangen=[Warteschlange(**w) for w in d.get("warteschlangen", [])])


# ── Leitstelle ───────────────────────────────────────────────────────────

class Leitstelle:
    """Verwaltung (ohne Schlüssel, aus dem Heimnetz) und Fassade (mit dem Schlüssel der Abnahme)."""

    def __init__(self, haus: Haus):
        # HTTPS mit Prüfung gegen die Hausstelle (wie das Ausrollen): mkcert -CAROOT
        hausstelle = ssl.create_default_context(cafile=str(Path(shell("mkcert -CAROOT")) / "rootCA.pem"))
        self.verwaltung = httpx.Client(base_url=haus.leitstelle + "/api", verify=hausstelle, timeout=60)
        self.fassade = httpx.Client(base_url=haus.leitstelle, verify=hausstelle, timeout=600,
                                    headers={"Authorization": f"Bearer {haus.schluessel}", "X-Leitstelle-Titel": TITEL.replace(" ", "%20")})

    def lage(self) -> dict:
        return self.verwaltung.get("/lage").raise_for_status().json()

    def auskunft(self) -> dict:
        return self.fassade.get("/v1/lage").raise_for_status().json()

    def auftrag(self, kennung: str) -> dict:
        return self.verwaltung.get(f"/auftraege/{kennung}").raise_for_status().json()

    def knotenname(self, kennung: str | None) -> str | None:
        return next((k["name"] for k in self.lage()["knoten"] if k["kennung"] == kennung), None)

    def knotenkennung(self, name: str) -> str:
        return next(k["kennung"] for k in self.lage()["knoten"] if k["name"] == name)

    def pruefung_oeffnen(self, dauer_s: float, grund: str) -> None:
        kennung = next(a["kennung"] for a in self.lage()["anwendungen"] if a["name"] == "Abnahme")
        self.verwaltung.post("/pruefung", json={"anwendung": kennung, "dauer_s": dauer_s, "grund": grund}).raise_for_status()

    def pruefung_schliessen(self) -> None:
        r = self.verwaltung.delete("/pruefung")
        if r.status_code not in (200, 409):                    # 409: schon zu (Frist)
            r.raise_for_status()

    def akku(self, rechner: str, prozent: int | None) -> None:
        self.verwaltung.put("/pruefung/akku", json={"knoten": self.knotenkennung(rechner), "prozent": prozent}).raise_for_status()


# ── Ergebnisse ───────────────────────────────────────────────────────────

@dataclass
class Ergebnis:
    nr: str
    ticket: str
    was: str
    erwartet: str
    gesehen: str = ""
    ok: bool = False
    dauer_s: float = 0.0
    notizen: list[str] = field(default_factory=list)


def warten_bis(bedingung: Callable[[], object], frist_s: float, takt_s: float = 2.0) -> object:
    ende = time.monotonic() + frist_s
    while time.monotonic() < ende:
        if (wert := bedingung()):
            return wert
        time.sleep(takt_s)
    return None


def shell(befehl: str, eingabe: str = "") -> str:
    r = subprocess.run(befehl, shell=True, input=eingabe, capture_output=True, text=True, timeout=1900)
    if r.returncode != 0:
        raise RuntimeError(f"{befehl[:60]}...: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


# ── Szenarien ────────────────────────────────────────────────────────────

class Abnahme:
    def __init__(self, haus: Haus, ls: Leitstelle):
        self.haus, self.ls = haus, ls
        self.klein, self.gross = haus.rechner["klein"], haus.rechner["gross"]
        self.fenster_auf_s = time.time()          # beim Öffnen des Fensters neu gesetzt

    def sprechen(self, text: str) -> tuple[httpx.Response, str | None]:
        r = self.ls.fassade.post(f"/v1/dienste/{self.haus.modelle['sprechen']}/v1/audio/speech",
                                 json={"model": self.haus.modelle["sprechen"], "input": text, "voice": self.haus.modelle["stimme"]})
        return r, r.headers.get("X-Leitstelle-Auftrag")

    def einbetten(self, texte: list[str]) -> tuple[httpx.Response, str | None]:
        r = self.ls.fassade.post("/v1/embeddings", json={"model": self.haus.modelle["einbettung"], "input": texte})
        return r, r.headers.get("X-Leitstelle-Auftrag")

    def rechner_des(self, kennung: str | None) -> str | None:
        return self.ls.knotenname(self.ls.auftrag(kennung).get("knoten")) if kennung else None

    def geladen_auf(self, rechner: str, familie: str) -> bool:
        r = next(x for x in self.ls.auskunft()["rechner"] if x["name"] == rechner)
        return any(m["familie"] == familie for m in r["modelle"])

    # L1 (LS-19): ohne Modell, mit Platzhalter
    def l1_modellpflicht(self, e: Ergebnis) -> None:
        ohne = self.ls.fassade.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "Hallo"}]})
        auto = self.ls.fassade.post("/v1/chat/completions", json={"model": "auto", "messages": [{"role": "user", "content": "Hallo"}]})
        code_ohne = (ohne.json().get("error") or {}).get("code")
        code_auto = (auto.json().get("error") or {}).get("code")
        e.gesehen = f"ohne Modell {ohne.status_code} {code_ohne}; 'auto' {auto.status_code} {code_auto}"
        e.ok = ohne.status_code == 400 and code_ohne == "modell_fehlt" and auto.status_code == 404 and code_auto == "kein_modell"

    # L2 (LS-18, LS-20): Auskunft mit offenem Fenster, ohne Inhalte
    def l2_auskunft(self, e: Ergebnis) -> None:
        a = self.ls.auskunft()
        text = json.dumps(a, ensure_ascii=False)
        p = a.get("pruefung") or {}
        e.gesehen = f"Prüffenster für {p.get('anwendung')}, Durchlass {p.get('durchlass')}; Titel im Text: {'ja' if 'geheim' in text else 'nein'}"
        e.ok = p.get("anwendung") == "Abnahme" and "geheim" not in text and {"apps", "rechner", "rangfolge"} <= set(a)

    # L3 (LS-17, LS-16): Akku gesperrt -> Sprache auf dem großen Mac; frei -> auf dem kleinen (Rolle)
    def l3_akku_und_rolle(self, e: Ergebnis) -> None:
        self.ls.akku(self.klein, 20)
        r1, k1 = self.sprechen("Erster Satz der Abnahme.")
        bei_sperre = self.rechner_des(k1)
        self.ls.akku(self.klein, 75)
        r2, k2 = self.sprechen("Zweiter Satz der Abnahme.")
        frei = self.rechner_des(k2)
        e.gesehen = f"Akku 20 %: {r1.status_code} auf {bei_sperre}; Akku 75 %: {r2.status_code} auf {frei}"
        e.ok = r1.status_code == r2.status_code == 200 and bei_sperre == self.gross and frei == self.klein

    # L4 (LS-15): Vorrang der Sprache auf ihrem Rechner, Nachlauf
    def l4_vorrang(self, e: Ergebnis) -> None:
        r, k = self.sprechen("Ein etwas längerer Satz, damit der Vorrang während des Sprechens sichtbar bleibt.")
        rechner = self.rechner_des(k)
        ende = time.monotonic()
        vorrang = lambda: next((x.get("vorrang") for x in self.ls.auskunft()["rechner"] if x["name"] == rechner), None)
        gleich = vorrang()
        nachlauf = self.haus.fristen["vorrang_nachlauf_s"]
        weg = warten_bis(lambda: not vorrang(), nachlauf + 30, 2)
        nach_s = time.monotonic() - ende
        e.gesehen = f"Sprache {r.status_code} auf {rechner}; direkt danach Vorrang {gleich!r}; frei nach {nach_s:.0f} s"
        e.ok = r.status_code == 200 and bool(gleich) and weg is not None and nach_s >= nachlauf - 5

    # L5 (Einbettung): rechnet für die Abnahme auch im Fenster
    def l5_einbettung(self, e: Ergebnis) -> None:
        r, k = self.einbetten(["Abnahme eins", "Abnahme zwei"])
        anzahl = len(r.json().get("data", [])) if r.status_code == 200 else 0
        e.gesehen = f"{r.status_code}, {anzahl} Vektoren, auf {self.rechner_des(k)}"
        e.ok = r.status_code == 200 and anzahl == 2
        self._einbettung_rechner = self.rechner_des(k)

    # L6 (LS-14): nach dem letzten Auftrag entladen
    def l6_entladen(self, e: Ergebnis) -> None:
        r, k = self.einbetten(["Letzter Auftrag vor dem Entladen"])
        rechner = self.rechner_des(k)
        ende = time.monotonic()
        familie = self.haus.modelle["einbettung"]
        frist = self.haus.fristen["entladen_s"]
        weg = warten_bis(lambda: not self.geladen_auf(rechner, familie), frist + self.haus.fristen["entladen_spielraum_s"], 3)
        nach_s = time.monotonic() - ende
        e.gesehen = f"{familie} auf {rechner}: {'entladen' if weg else 'noch geladen'} nach {nach_s:.0f} s"
        e.ok = r.status_code == 200 and weg is not None and nach_s >= frist - 5

    # L7 (LS-20): Live-Arbeit wartet mit Grund, Sprache ausgenommen
    def l7_live_haelt(self, e: Ergebnis) -> None:
        lage = self.ls.lage()
        abnahme = next(a["kennung"] for a in lage["anwendungen"] if a["name"] == "Abnahme")
        fremde = [a for a in lage["auftraege"] if a["anwendung"] != abnahme and a["zustand"] in ("laeuft", "zugeteilt") and a["faehigkeit"] != "stimme"
                  and (a.get("start_s") or 0) > self.fenster_auf_s]
        gehalten = [a for a in lage["auftraege"] if "Abnahme im Betrieb" in (a.get("begruendung") or "")]
        e.gesehen = f"{len(gehalten)} Live-Aufträge warten mit Grund; {len(fremde)} fremde seit dem Öffnen gestartet"
        e.ok = not fremde

    SZENARIEN = [
        ("L1", "LS-19", "Modellpflicht", "ohne Modell 400 modell_fehlt, Platzhalter 'auto' 404 kein_modell", "l1_modellpflicht"),
        ("L2", "LS-18", "Auskunft im Fenster", "Prüffenster der Abnahme sichtbar, keine Titel", "l2_auskunft"),
        ("L3", "LS-17, LS-16", "Akku und Rolle", "Akku 20 %: Sprache auf dem großen Mac; 75 %: auf dem kleinen (Rolle)", "l3_akku_und_rolle"),
        ("L4", "LS-15", "Vorrang der Sprache", "Vorrang auf dem Rechner der Sprache, frei erst nach dem Nachlauf", "l4_vorrang"),
        ("L5", "LS-16", "Einbettung im Fenster", "Einbettung der Abnahme rechnet", "l5_einbettung"),
        ("L6", "LS-14", "Entladen nach dem letzten Auftrag", "Einbettungsmodell nach der Frist entladen, nicht vorher", "l6_entladen"),
        ("L7", "LS-20", "Live-Arbeit hält", "keine fremde Arbeit außer Sprache startet im Fenster", "l7_live_haelt"),
    ]

    def fahren(self, nur: set[str] | None) -> list[Ergebnis]:
        aus: list[Ergebnis] = []
        for nr, ticket, was, erwartet, methode in self.SZENARIEN:
            if nur and nr not in nur:
                continue
            e = Ergebnis(nr, ticket, was, erwartet)
            start = time.monotonic()
            try:
                getattr(self, methode)(e)
            except Exception as f:              # ein Szenario darf die übrigen nicht verhindern
                e.gesehen, e.ok = f"Fehler: {f}", False
            e.dauer_s = time.monotonic() - start
            print(f"{nr} {'ok' if e.ok else 'FEHLER'}: {e.gesehen}", flush=True)
            aus.append(e)
        return aus


# ── Rahmen: anhalten, Fenster, Szenarien, alles zurück ───────────────────

def bericht(ergebnisse: list[Ergebnis], notizen: list[str], fassung: str) -> str:
    gut = sum(e.ok for e in ergebnisse)
    zeilen = [f"Abnahme der Arbeitslogik im Betrieb, Leitstelle {fassung}, {time.strftime('%d.%m.%Y %H:%M')}: {gut} von {len(ergebnisse)} bestanden.", "",
              "| Nr | Ticket | Was | Erwartet | Gesehen | Ergebnis |", "|---|---|---|---|---|---|"]
    zeilen += [f"| {e.nr} | {e.ticket} | {e.was} | {e.erwartet} | {e.gesehen} | {'bestanden' if e.ok else 'NICHT bestanden'} |" for e in ergebnisse]
    if notizen:
        zeilen += ["", "Ablauf:"] + [f"- {n}" for n in notizen]
    return "\n".join(zeilen)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--haus", type=Path, default=WURZEL / "privat" / "abnahme.toml")
    p.add_argument("--nur", default="", help="nur diese Szenarien, etwa L1,L3")
    p.add_argument("--bericht-ans-ticket", action="store_true")
    w = p.parse_args(argv)
    haus = Haus.laden(w.haus)
    ls = Leitstelle(haus)
    nur = {x.strip() for x in w.nur.split(",") if x.strip()} or None
    notizen: list[str] = []
    abnahme = Abnahme(haus, ls)
    ergebnisse: list[Ergebnis] = []
    fassung = ls.lage()["version"]
    try:
        for q in haus.warteschlangen:
            if q.stand and q.angehalten_wenn and q.angehalten_wenn in shell(q.stand):
                notizen.append(f"{q.name}: war schon angehalten, bleibt so")
                continue
            q.vorher, q.angefasst = shell(q.anhalten), True
            notizen.append(f"{q.name}: Warteschlange angehalten")
        ls.pruefung_oeffnen(haus.dauer_s, "Abnahme LS-20")
        abnahme.fenster_auf_s = time.time()
        notizen.append("Prüffenster offen")
        abnahme_kennung = next(a["kennung"] for a in ls.lage()["anwendungen"] if a["name"] == "Abnahme")
        frei = warten_bis(lambda: not [a for a in ls.lage()["auftraege"] if a["zustand"] in ("laeuft", "zugeteilt")
                                       and a["anwendung"] != abnahme_kennung and a["faehigkeit"] != "stimme"], haus.fristen["ruhe_warten_s"], 5)
        notizen.append("Live-Arbeit ausgelaufen" if frei else f"Live-Arbeit lief nach {haus.fristen['ruhe_warten_s']:.0f} s noch; Szenarien trotzdem gefahren")
        ergebnisse = abnahme.fahren(nur)
    finally:
        for rechner in haus.rechner.values():
            try:
                ls.akku(rechner, None)
            except httpx.HTTPError:
                pass                              # Fenster schon zu: dann gilt ohnehin der Messwert
        ls.pruefung_schliessen()
        notizen.append("Probewerte zurück, Prüffenster geschlossen")
        for q in haus.warteschlangen:
            if q.angefasst:
                shell(q.fortsetzen, q.vorher if q.zustand_weiterreichen else "")
                notizen.append(f"{q.name}: Warteschlange fortgesetzt")
    text = bericht(ergebnisse, notizen, fassung)
    ziel = WURZEL / "privat" / "abnahmen" / time.strftime("abnahme-%Y%m%d-%H%M.md")
    ziel.parent.mkdir(exist_ok=True)
    ziel.write_text(text + "\n", encoding="utf-8")
    print("\n" + text + f"\n\nBericht: {ziel}")
    if w.bericht_ans_ticket:
        subprocess.run([sys.executable, str(TICKET), "kommentar", haus.ticket, text], check=False)
    return 0 if ergebnisse and all(e.ok for e in ergebnisse) else 1


if __name__ == "__main__":
    sys.exit(main())
