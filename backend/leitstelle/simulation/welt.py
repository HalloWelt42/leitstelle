"""Die Schein-Welt: Zeit, Attrappen der Dienste, Vollzug für die Leitstelle, Kennzahlen."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..kern.leitstelle import Leitstelle
from ..kern.messungen import Messwerk
from ..kern.modelle import Auftrag, Verbund
from ..kern.regeln.auswerter import Regelgraph
from ..kern.werte import Auftragszustand, Dienstzustand, Faehigkeit, Hintergrundstufe, Massnahmenzustand, Modellzustand, Prioritaet


@dataclass
class Wahrheit:
    """Was nur die Welt weiß: wahre Lade- und Startzeiten. Die Leitstelle muss sie messen."""

    ladezeit: dict[str, float] = field(default_factory=dict)      # "familie@knoten" -> s
    startzeit: dict[str, float] = field(default_factory=dict)     # dienst -> s
    ladezeit_je_gb: float = 0.35

    def lade(self, familie: str, knoten: str, gb: float) -> float:
        return self.ladezeit.get(f"{familie}@{knoten}", max(4.0, gb * self.ladezeit_je_gb))

    def start(self, dienst: str, vorgabe: float) -> float:
        return self.startzeit.get(dienst, vorgabe)


@dataclass
class Welt:
    verbund: Verbund
    messwerk: Messwerk = field(default_factory=Messwerk)
    wahrheit: Wahrheit = field(default_factory=Wahrheit)
    leitstelle: Leitstelle = field(default_factory=Leitstelle)
    ankuenfte: list[tuple[float, Auftrag]] = field(default_factory=list)
    ladevorgaenge: dict[str, tuple[float, float]] = field(default_factory=dict)   # modell -> (start, dauer)
    startvorgaenge: dict[str, tuple[float, float]] = field(default_factory=dict)  # dienst -> (start, dauer)
    signale: list[tuple[float, str, str, dict]] = field(default_factory=list)
    meldungen: list[tuple[float, str]] = field(default_factory=list)
    beendet: list[tuple[float, str, int]] = field(default_factory=list)   # (Zeit, Knoten, pid): Arbeiter des Läufers beenden lassen
    laufnummer: int = 0

    @classmethod
    def mit(cls, verbund: Verbund, graphen: list[Regelgraph] | None = None) -> "Welt":
        return cls(verbund=verbund, leitstelle=Leitstelle(graphen))

    # ── Aufträge anlegen ─────────────────────────────────────────────────
    def auftrag(self, anwendung: str, faehigkeit: Faehigkeit, laufzeit_s: float = 20.0, zeit_s: float | None = None,
                prioritaet: Prioritaet | None = None, festes_modell: str | None = None, kennung: str | None = None,
                extern: list[str] | None = None) -> Auftrag:
        self.laufnummer += 1
        app = self.verbund.anwendungen[anwendung]
        a = Auftrag(kennung=kennung or f"a-{self.laufnummer:04d}", anwendung=anwendung, faehigkeit=faehigkeit,
                    prioritaet=app.prioritaet if prioritaet is None else prioritaet, eingang_s=self.verbund.zeit_s if zeit_s is None else zeit_s,
                    laufzeit_s=laufzeit_s, festes_modell=festes_modell, extern_familien=list(extern or []))
        if zeit_s is None or zeit_s <= self.verbund.zeit_s:
            self.verbund.auftraege[a.kennung] = a
        else:
            self.ankuenfte.append((zeit_s, a))
        return a

    # ── Vollzug (Schnittstelle für die Leitstelle) ───────────────────────
    def dienst_starten(self, dienst: str) -> None:
        d = self.verbund.dienste[dienst]
        if d.zustand == Dienstzustand.AUS and d.installiert:
            d.zustand = Dienstzustand.STARTET
            self.startvorgaenge[dienst] = (self.verbund.zeit_s, self.wahrheit.start(dienst, d.startzeit_s))

    def modell_laden(self, modell: str) -> None:
        m = self.verbund.modelle[modell]
        d = self.verbund.dienste[m.dienst]
        if d.extern:
            m.zustand = Modellzustand.GELADEN
            return
        if m.zustand == Modellzustand.FREI:
            m.zustand = Modellzustand.LAEDT
            m.geladen_seit_s = self.verbund.zeit_s
            self.ladevorgaenge[modell] = (self.verbund.zeit_s, self.wahrheit.lade(m.familie, d.knoten or "", m.gb))

    def instanz_starten(self, dienst: str, familie: str, vorbild: str) -> None:
        """Wie der Maschinenraum: eine weitere Instanz als eigenes Modell derselben Familie, startet wie ein Laden."""
        v = self.verbund.modelle[vorbild]
        stufe = next(n for n in range(2, 1000) if f"{familie}.{n}@{dienst}" not in self.verbund.modelle)
        kennung = f"{familie}.{stufe}@{dienst}"
        self.verbund.modelle[kennung] = v.model_copy(update={"kennung": kennung, "name": f"{v.name} ({stufe})", "zustand": Modellzustand.FREI,
                                                            "zusatz": True, "auftraege_aktiv": 0, "geladen_seit_s": None, "letzte_nutzung_s": None})
        self.modell_laden(kennung)

    def modell_entladen(self, modell: str) -> None:
        m = self.verbund.modelle[modell]
        assert m.zustand != Modellzustand.RECHNET, "rechnendes Modell darf nie entladen werden"
        m.zustand = Modellzustand.FREI
        m.geladen_seit_s = None
        m.auftraege_aktiv = 0
        self.ladevorgaenge.pop(modell, None)

    def auftrag_umleiten(self, auftrag: str, dienst: str, modell: str, knoten: str | None) -> None:
        a = self.verbund.auftraege[auftrag]
        a.dienst, a.modell, a.knoten = dienst, modell, knoten
        a.umgeleitet += 1
        a.zustand = Auftragszustand.ZUGETEILT
        a.wartet_auf_familie = a.wartet_auf_knoten = None
        a.voraussichtlich_s = None
        m = self.verbund.modelle[modell]
        if m.zustand == Modellzustand.FREI:
            self.modell_laden(modell)
        self.signal(a.anwendung, "auftrag.laeuft", {"auftrag": auftrag, "knoten": knoten})

    def auftrag_extern(self, auftrag: str, dienst: str, modell: str) -> None:
        a = self.verbund.auftraege[auftrag]
        a.dienst, a.modell, a.knoten, a.extern = dienst, modell, None, True
        a.umgeleitet += 1
        a.zustand = Auftragszustand.ZUGETEILT
        a.wartet_auf_familie = a.wartet_auf_knoten = None
        self.verbund.modelle[modell].zustand = Modellzustand.GELADEN
        self.signal(a.anwendung, "auftrag.laeuft", {"auftrag": auftrag, "zone": "extern"})

    def melden(self, text: str) -> None:
        self.meldungen.append((self.verbund.zeit_s, text))
        self.verbund.melden(text)

    def signal(self, anwendung: str, art: str, nutzlast: dict) -> None:
        self.signale.append((self.verbund.zeit_s, anwendung, art, nutzlast))

    def laufende_abbrechen_mit_teilergebnis(self, knoten: str) -> None:
        for a in self.verbund.auftraege.values():
            if a.knoten == knoten and a.zustand in (Auftragszustand.LAEUFT, Auftragszustand.ZUGETEILT):
                a.zustand = Auftragszustand.ABGEBROCHEN
                a.teilergebnis = a.fortschritt_s > 0
                a.ende_s = self.verbund.zeit_s
                if a.modell:
                    m = self.verbund.modelle[a.modell]
                    m.auftraege_aktiv = max(0, m.auftraege_aktiv - 1)
                    if m.auftraege_aktiv == 0 and m.zustand == Modellzustand.RECHNET:
                        m.zustand = Modellzustand.GELADEN
                self.signal(a.anwendung, "auftrag.abgebrochen", {"auftrag": a.kennung, "teilergebnis": a.teilergebnis, "grund": "knoten_ausgefallen"})

    def wartende_neu_einreihen(self, knoten: str) -> None:
        for a in self.verbund.auftraege.values():
            if a.wartet and (a.wartet_auf_knoten == knoten or a.knoten == knoten):
                a.zustand = Auftragszustand.EINGEREIHT
                a.dienst = a.modell = a.knoten = None
                a.wartet_auf_familie = a.wartet_auf_knoten = None
                a.voraussichtlich_s = None

    def bevorzugter_knoten(self, knoten: str | None) -> None:
        self.verbund.hintergrund_knoten_bevorzugt = knoten

    def laeufer_prozess_beenden(self, knoten: str, pid: int) -> None:
        """Wie der Betrieb: vermerken, dass er beendet wird; weg ist er erst mit der nächsten Meldung des Maschinenraums."""
        self.beendet.append((self.verbund.zeit_s, knoten, pid))
        last = self.verbund.knoten[knoten].last
        for p in last.prozesse if last else []:
            if p.pid == pid:
                p.beenden_s = self.verbund.zeit_s

    def hintergrund_stufe(self, knoten: str, stufe: Hintergrundstufe, grund: str) -> None:
        k = self.verbund.knoten[knoten]
        k.hintergrund_stufe, k.hintergrund_grund, k.hintergrund_seit_s = stufe, grund, self.verbund.zeit_s

    def hintergrund(self, an: bool) -> None:
        self.verbund.hintergrund_an = an
        if not an:
            for a in self.verbund.auftraege.values():
                if a.prioritaet == Prioritaet.HINTERGRUND and a.zustand == Auftragszustand.LAEUFT and a.anhaltbar:
                    a.zustand = Auftragszustand.PAUSIERT
                    m = self.verbund.modelle[a.modell] if a.modell else None
                    if m:
                        m.auftraege_aktiv = max(0, m.auftraege_aktiv - 1)
                        if m.auftraege_aktiv == 0:
                            m.zustand = Modellzustand.GELADEN
        else:
            for a in self.verbund.auftraege.values():
                if a.zustand == Auftragszustand.PAUSIERT:
                    a.zustand = Auftragszustand.ZUGETEILT

    # ── Zeit ─────────────────────────────────────────────────────────────
    def schritt(self, dt: float = 1.0) -> None:
        v = self.verbund
        v.zeit_s += dt
        # Ankünfte
        faellig = [x for x in self.ankuenfte if x[0] <= v.zeit_s]
        for zeit, a in faellig:
            a.eingang_s = zeit
            v.auftraege[a.kennung] = a
            self.ankuenfte.remove((zeit, a))
        # Dienste starten
        for dk, (start, dauer) in list(self.startvorgaenge.items()):
            if v.zeit_s - start >= dauer:
                v.dienste[dk].zustand = Dienstzustand.BEREIT
                self.messwerk.merke_startzeit(dk, v.zeit_s - start)
                del self.startvorgaenge[dk]
        # Modelle laden
        for mk, (start, dauer) in list(self.ladevorgaenge.items()):
            m = v.modelle[mk]
            if m.zustand != Modellzustand.LAEDT:
                del self.ladevorgaenge[mk]
                continue
            if v.zeit_s - start >= dauer:
                m.zustand = Modellzustand.GELADEN
                m.geladen_seit_s = v.zeit_s
                knoten = v.dienste[m.dienst].knoten or ""
                self.messwerk.merke_ladezeit(m.familie, knoten, v.zeit_s - start)
                del self.ladevorgaenge[mk]
        # Pausierter Hintergrund: nach der Fairness-Frist wieder zuteilen
        for a in v.auftraege.values():
            if a.zustand == Auftragszustand.PAUSIERT and v.zeit_s - a.eingang_s >= v.regelwerk.hintergrund_spaetestens_s:
                a.zustand = Auftragszustand.ZUGETEILT
        # Zugeteilte starten, wenn Modell bereit und Platz frei
        for a in sorted((x for x in v.auftraege.values() if x.zustand == Auftragszustand.ZUGETEILT), key=lambda x: (-int(x.prioritaet), x.eingang_s)):
            m = v.modelle[a.modell] if a.modell else None
            d = v.dienste[a.dienst] if a.dienst else None
            if m is None or d is None or not d.nutzbar:
                continue
            if m.zustand not in (Modellzustand.GELADEN, Modellzustand.RECHNET):
                continue
            if m.auftraege_aktiv >= d.plaetze:
                continue
            a.zustand = Auftragszustand.LAEUFT
            a.start_s = v.zeit_s
            m.auftraege_aktiv += 1
            m.zustand = Modellzustand.RECHNET
            m.letzte_nutzung_s = v.zeit_s
        # Laufende rechnen
        for a in list(v.auftraege.values()):
            if a.zustand != Auftragszustand.LAEUFT:
                continue
            a.fortschritt_s += dt
            if a.fortschritt_s >= a.laufzeit_s:
                a.zustand = Auftragszustand.FERTIG
                a.ende_s = v.zeit_s
                m = v.modelle[a.modell]
                m.auftraege_aktiv = max(0, m.auftraege_aktiv - 1)
                m.letzte_nutzung_s = v.zeit_s
                if m.auftraege_aktiv == 0:
                    m.zustand = Modellzustand.GELADEN
                self.messwerk.merke_laufzeit(a.anwendung, a.faehigkeit.value, a.laufzeit_s)
        # Leitstelle im Takt
        if int(v.zeit_s) % int(v.regelwerk.umschichter_takt_s) == 0:
            self.leitstelle.takt(v, self.messwerk, self)

    def laufen(self, sekunden: float) -> None:
        for _ in range(int(sekunden)):
            self.schritt()

    def laufen_bis_fertig(self, hoechstens_s: float = 3600.0) -> float:
        """Läuft, bis kein Auftrag mehr offen ist, und gibt die gebrauchte Zeit zurück."""
        start = self.verbund.zeit_s
        while self.verbund.zeit_s - start < hoechstens_s:
            if not self.verbund.offene_auftraege() and not self.ankuenfte:
                break
            self.schritt()
        return self.verbund.zeit_s - start

    # ── Kennzahlen ───────────────────────────────────────────────────────
    def wartezeit(self, kennung: str) -> float | None:
        a = self.verbund.auftraege[kennung]
        return None if a.start_s is None else a.start_s - a.eingang_s

    def ausgefuehrte(self) -> list:
        return [m for m in self.verbund.massnahmen if m.zustand == Massnahmenzustand.AUSGEFUEHRT]

    def wechsel_je_familie_knoten(self) -> dict[str, int]:
        zaehler: dict[str, int] = {}
        for m in self.ausgefuehrte():
            if m.richtung in ("laden", "entladen") and m.modell and m.knoten:
                k = f"{m.modell}@{m.knoten}"
                zaehler[k] = zaehler.get(k, 0) + 1
        return zaehler
