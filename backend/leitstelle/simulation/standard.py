"""Der Standard-Verbund für Tests: 5 Anbindungen, 8 Anwendungen, 4 Knoten.

Anbindungen: Modell-Läufer auf dem großen Mac, Modell-Läufer auf dem kleinen Mac (installiert,
aus), txt2voice auf dem großen Mac, Hörer auf dem kleinen Mac, externer Anbieter.
Zahlen folgen einem echten Haus (Bestand des Autors): 128 und 32 GB, 80B-Modell 84,7 GB,
Bildmodell 11,8 GB, Einbettung 1,1 GB und so weiter.
"""

from __future__ import annotations

from ..kern.modelle import Anwendung, Dienst, Knoten, Modell, Regelwerk, Verbund
from ..kern.werte import Dienstzustand, Faehigkeit as F, Modellzustand, Prioritaet as P, Zone
from .welt import Welt


def standard_verbund(regelwerk: Regelwerk | None = None) -> Verbund:
    v = Verbund(regelwerk=regelwerk or Regelwerk())
    v.knoten = {k.kennung: k for k in [
        Knoten(kennung="mac-128", name="Mac Studio", zone=Zone.HEIM, speicher_gb=128, system_gb=32),
        Knoten(kennung="mac-32", name="MacBook", zone=Zone.HEIM, speicher_gb=32, system_gb=6, hintergrund_fenster=(23, 7), budget_fest_gb=24),
        Knoten(kennung="pi-archiv", name="Pi Archiv", zone=Zone.HEIM, speicher_gb=8, system_gb=2),
        Knoten(kennung="server-fern", name="Server Helsinki", zone=Zone.FERN, speicher_gb=8, system_gb=3),
    ]}
    v.dienste = {d.kennung: d for d in [
        Dienst(kennung="laeufer-128", name="Modell-Läufer Mac Studio", knoten="mac-128", art="openai_kompatibel", faehigkeiten={F.TEXT, F.EINBETTUNG, F.UEBERSETZEN, F.BILD_BESCHREIBEN}),
        Dienst(kennung="laeufer-32", name="Modell-Läufer MacBook", knoten="mac-32", art="openai_kompatibel", faehigkeiten={F.TEXT, F.UEBERSETZEN, F.BILD_BESCHREIBEN}, zustand=Dienstzustand.AUS, installiert=True, startzeit_s=3.0),
        Dienst(kennung="txt2voice", name="txt2voice", knoten="mac-128", art="txt2voice", faehigkeiten={F.HOEREN, F.STIMME}),
        Dienst(kennung="hoerer-32", name="Hörer MacBook", knoten="mac-32", art="hoeren_http", faehigkeiten={F.HOEREN}),
        Dienst(kennung="extern-anbieter", name="Externer Anbieter", knoten=None, art="extern_openai", faehigkeiten={F.TEXT, F.BILD_BESCHREIBEN}, extern=True, plaetze=4),
    ]}
    def m(kennung, name, dienst, familie, faehigkeiten, gb, mrd, zustand=Modellzustand.FREI, fest=False):
        f = set(faehigkeiten) if isinstance(faehigkeiten, (set, list, tuple)) else {faehigkeiten}
        return Modell(kennung=kennung, name=name, dienst=dienst, familie=familie, faehigkeiten=f, gb=gb, parameter_mrd=mrd, zustand=zustand, geschuetzt_fest=fest,
                      geladen_seit_s=-100000.0 if zustand != Modellzustand.FREI else None, letzte_nutzung_s=-100000.0 if zustand != Modellzustand.FREI else None)
    v.modelle = {x.kennung: x for x in [
        # Mac Studio, Modell-Läufer
        m("qwen80@128", "Qwen3 Next 80B", "laeufer-128", "qwen-next-80b", {F.TEXT, F.UEBERSETZEN}, 84.7, 80, Modellzustand.GELADEN),
        m("bge@128", "bge-m3 Einbettung", "laeufer-128", "bge-m3", F.EINBETTUNG, 1.1, 0.6, Modellzustand.GELADEN, fest=True),
        m("glm@128", "GLM 4.6V Flash", "laeufer-128", "glm-4.6v", F.BILD_BESCHREIBEN, 11.8, 9),
        m("gemma@128", "Gemma 4 26B", "laeufer-128", "gemma-4-26b", F.BILD_BESCHREIBEN, 16.2, 26),
        m("coder@128", "Qwen3 Coder Next", "laeufer-128", "qwen-coder-next", F.TEXT, 46.3, 80),
        m("klein@128", "Qwen3 4B", "laeufer-128", "qwen-4b", {F.TEXT, F.UEBERSETZEN}, 2.5, 4),
        # MacBook, Modell-Läufer (heruntergeladen, Dienst aus)
        m("glm@32", "GLM 4.6V Flash", "laeufer-32", "glm-4.6v", F.BILD_BESCHREIBEN, 11.8, 9),
        m("gemma@32", "Gemma 4 26B", "laeufer-32", "gemma-4-26b", F.BILD_BESCHREIBEN, 16.2, 26),
        m("klein@32", "Qwen3 4B", "laeufer-32", "qwen-4b", {F.TEXT, F.UEBERSETZEN}, 2.5, 4),
        # txt2voice
        m("whisper@128", "Whisper groß v3", "txt2voice", "whisper-gross", F.HOEREN, 3.1, 1.5, Modellzustand.GELADEN, fest=True),
        m("xtts@128", "Stimmklon", "txt2voice", "xtts", F.STIMME, 1.9, 0.5, Modellzustand.GELADEN, fest=True),
        # Hörer MacBook
        m("whisperm@32", "Whisper mittel", "hoerer-32", "whisper-mittel", F.HOEREN, 1.5, 0.8, Modellzustand.GELADEN, fest=True),
        # extern
        m("qwen35@extern", "Qwen3.6 35B (extern)", "extern-anbieter", "qwen-35b-extern", F.TEXT, 0, 35, Modellzustand.GELADEN),
        m("qwen27@extern", "Qwen3.8 27B (extern)", "extern-anbieter", "qwen-27b-extern", F.BILD_BESCHREIBEN, 0, 27, Modellzustand.GELADEN),
    ]}
    heim = {Zone.HEIM}
    heim_fern = {Zone.HEIM, Zone.FERN}
    alle = {Zone.HEIM, Zone.FERN, Zone.EXTERN}
    v.anwendungen = {a.kennung: a for a in [
        Anwendung(kennung="zusage", name="Zusage", prioritaet=P.HOCH, faehigkeiten={F.TEXT, F.BILD_BESCHREIBEN}, zonen=heim_fern,
                  ketten={F.TEXT: ["qwen-next-80b", "qwen-4b"], F.BILD_BESCHREIBEN: ["glm-4.6v", "gemma-4-26b"]}),
        Anwendung(kennung="tubevault", name="TubeVault", prioritaet=P.HINTERGRUND, faehigkeiten={F.HOEREN, F.STIMME, F.TEXT}, zonen=heim,
                  ketten={F.HOEREN: ["whisper-gross", "whisper-mittel"], F.STIMME: ["xtts"], F.TEXT: ["qwen-next-80b"]}),
        Anwendung(kennung="fundus", name="Fundus", prioritaet=P.NORMAL, faehigkeiten={F.TEXT, F.EINBETTUNG}, zonen=alle, extern_erlaubt=True,
                  ketten={F.TEXT: ["qwen-next-80b", "qwen-35b-extern"], F.EINBETTUNG: ["bge-m3"]}),
        Anwendung(kennung="medienpool", name="Medienpool", prioritaet=P.NORMAL, faehigkeiten={F.UEBERSETZEN}, zonen=heim,
                  ketten={F.UEBERSETZEN: ["qwen-next-80b", "qwen-4b"]}),
        Anwendung(kennung="kiste", name="Kiste", prioritaet=P.NORMAL, faehigkeiten={F.BILD_BESCHREIBEN, F.TEXT}, zonen=heim,
                  ketten={F.BILD_BESCHREIBEN: ["glm-4.6v", "gemma-4-26b"], F.TEXT: ["qwen-next-80b"]}),
        Anwendung(kennung="codehilfe", name="Codehilfe", prioritaet=P.HOCH, faehigkeiten={F.TEXT}, zonen=alle, extern_erlaubt=True,
                  ketten={F.TEXT: ["qwen-coder-next", "qwen-next-80b", "qwen-35b-extern"]}),
        Anwendung(kennung="rufzeichen", name="Rufzeichen", prioritaet=P.DRINGEND, faehigkeiten={F.TEXT, F.HOEREN, F.STIMME}, zonen=heim,
                  ketten={F.TEXT: ["qwen-next-80b", "qwen-4b"], F.HOEREN: ["whisper-mittel", "whisper-gross"], F.STIMME: ["xtts"]}),
        Anwendung(kennung="bildschmiede", name="Bildschmiede", prioritaet=P.HINTERGRUND, faehigkeiten={F.BILD_BESCHREIBEN, F.UEBERSETZEN}, zonen=heim,
                  ketten={F.BILD_BESCHREIBEN: ["gemma-4-26b", "glm-4.6v"], F.UEBERSETZEN: ["qwen-4b", "qwen-next-80b"]}),
    ]}
    return v


def standard_welt(regelwerk: Regelwerk | None = None, graphen=None) -> Welt:
    return Welt.mit(standard_verbund(regelwerk), graphen)
