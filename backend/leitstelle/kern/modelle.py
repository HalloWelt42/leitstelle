"""Fachmodell der Leitstelle: Knoten, Dienste, Modelle, Anwendungen, Aufträge, Regelwerk, Maßnahmen.

Alles Pydantic, nichts als rohes Dict. Der Verbund ist das Aggregat, über das Zuteiler,
Speicherplaner und Umschichter arbeiten. Zeiten sind Sekunden seit Start (float), damit der
Kern ohne echte Uhr läuft und im Schein-Verbund deterministisch bleibt.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .werte import (
    IM_SPEICHER,
    OFFENE_ZUSTAENDE,
    WARTENDE_ZUSTAENDE,
    Auftragszustand,
    Automatik,
    Betriebsmodus,
    Dienstzustand,
    Faehigkeit,
    Massnahmenart,
    Massnahmenzustand,
    Modellzustand,
    Prioritaet,
    Zone,
)


class Knoten(BaseModel):
    kennung: str
    name: str
    zone: Zone
    speicher_gb: float
    system_gb: float = 6.0            # was System und andere Programme belegen (Messwert des Agenten)
    erreichbar: bool = True
    hintergrund_fenster: tuple[int, int] | None = None   # Stunden (von, bis), in denen Hintergrundarbeit hierher darf
    budget_fest_gb: float | None = None                  # von Hand gesetztes Budget; sonst Gesamtspeicher minus Reserve

    def budget_gb(self, reserve_gb: float) -> float:
        """Speicher, den Modelle zusammen höchstens belegen dürfen."""
        if self.budget_fest_gb is not None:
            return max(0.0, min(self.budget_fest_gb, self.speicher_gb - self.system_gb))
        return max(0.0, self.speicher_gb - max(reserve_gb, self.system_gb))


class Dienst(BaseModel):
    kennung: str
    name: str
    knoten: str | None                # None = externer Anbieter
    art: str
    faehigkeiten: set[Faehigkeit]
    zustand: Dienstzustand = Dienstzustand.BEREIT
    installiert: bool = True
    startzeit_s: float = 3.0          # Vorgabe ohne Messung
    extern: bool = False
    plaetze: int = 1                  # gleichzeitige Aufträge je Modell
    anfragen_je_minute: int | None = None   # Grenze des Anbieters; die Leitstelle hält sie ein
    anfragen_s: list[float] = Field(default_factory=list)   # Zeitpunkte gesendeter Anfragen im gleitenden Fenster
    gesperrt_bis_s: float | None = None     # nach Überlast des Dienstes (429, extern auch 5xx)

    @property
    def nutzbar(self) -> bool:
        return self.zustand == Dienstzustand.BEREIT


class Modell(BaseModel):
    kennung: str
    name: str
    dienst: str
    familie: str                      # gleiches Modell auf mehreren Diensten trägt dieselbe Familie
    faehigkeiten: set[Faehigkeit]     # ein Textmodell kann auch übersetzen; eine Instanz, ein Speicherblock
    gb: float                         # Bedarf: damit wird geplant
    parameter_mrd: float
    zustand: Modellzustand = Modellzustand.FREI
    geschuetzt_fest: bool = False     # Einbettungsmodelle und ausdrücklich geschützte
    instanzen_hoechstens: int = 1     # so viele Instanzen darf die Leitstelle starten (Dienstdatei des Maschinenraums)
    zusatz: bool = False              # weitere Instanz (<familie>.<n>): weicht bei Speichermangel vor allen anderen
    schutz_vorgabe: bool | None = None  # vom Dienst vorgegeben (zum Beispiel Maschinenraum); geht der Regel vor
    gb_jetzt: float | None = None     # tatsächlich belegt, wenn gemessen; sonst gilt gb
    geladen_seit_s: float | None = None
    letzte_nutzung_s: float | None = None
    auftraege_aktiv: int = 0
    plaetze: int | None = None        # gleichzeitige Aufträge, wenn der Dienst es je Modell meldet; sonst die des Dienstes
    # Hat der Dienst das Laden abgelehnt (zu wenig Speicher, Fehler), wird bis dahin kein neuer Versuch geplant
    ladesperre_bis_s: float | None = None
    ladesperre_grund: str = ""

    def geschuetzt(self, schutzgrenze_mrd: float) -> bool:
        if self.schutz_vorgabe is not None:
            return self.schutz_vorgabe
        return self.geschuetzt_fest or self.parameter_mrd < schutzgrenze_mrd

    @property
    def belegt_gb(self) -> float:
        """Was das Modell gerade wirklich belegt: gemessen, sonst seine Größe."""
        return self.gb_jetzt if self.gb_jetzt is not None else self.gb

    def ladbar(self, jetzt_s: float) -> bool:
        """Darf jetzt ein Ladeversuch geplant werden? Nein, solange die Ladesperre läuft."""
        return self.ladesperre_bis_s is None or self.ladesperre_bis_s <= jetzt_s

    @property
    def im_speicher(self) -> bool:
        return self.zustand in IM_SPEICHER


class Anwendung(BaseModel):
    kennung: str
    name: str
    prioritaet: Prioritaet = Prioritaet.NORMAL
    faehigkeiten: set[Faehigkeit]
    zonen: set[Zone] = Field(default_factory=lambda: {Zone.HEIM})
    extern_erlaubt: bool = False
    ketten: dict[Faehigkeit, list[str]] = Field(default_factory=dict)   # Modellfamilien in Reihenfolge
    gleichzeitig: int = 4


class Auftrag(BaseModel):
    kennung: str
    anwendung: str
    faehigkeit: Faehigkeit
    prioritaet: Prioritaet
    eingang_s: float
    zustand: Auftragszustand = Auftragszustand.EINGEREIHT
    festes_modell: str | None = None  # Familie, wenn die Anwendung ein Modell verlangt
    modell: str | None = None
    dienst: str | None = None
    knoten: str | None = None
    laufzeit_s: float = 20.0          # wahre Dauer (nur der Schein-Verbund kennt sie; die Leitstelle schätzt)
    fortschritt_s: float = 0.0
    start_s: float | None = None
    ende_s: float | None = None
    umgeleitet: int = 0
    anhaltbar: bool = True
    begruendung: str = ""
    extern: bool = False
    # vom Zuteiler gesetzt, damit die Regeln wissen, worauf ein Auftrag wartet
    wartet_auf_familie: str | None = None
    wartet_auf_knoten: str | None = None
    voraussichtlich_s: float | None = None
    teilergebnis: bool = False
    grund: str | None = None          # Wort aus PROTOKOLL.md Abschnitt 7, wenn abgelehnt oder abgebrochen
    arbeit: str | None = None         # Arbeit der Anwendung, zu der die Anfrage gehört (Kopf X-Leitstelle-Arbeit)
    extern_familien: list[str] = Field(default_factory=list)   # Erlaubnisliste der App für externe Modelle (Kopf X-Leitstelle-Extern)
    feste_instanz: str | None = None  # Folgeaufruf an genau diese Modellinstanz (Kopf X-Leitstelle-Instanz)

    @property
    def offen(self) -> bool:
        return self.zustand in OFFENE_ZUSTAENDE

    @property
    def wartet(self) -> bool:
        return self.zustand in WARTENDE_ZUSTAENDE


class Arbeit(BaseModel):
    """Eine Arbeit einer Anwendung, die aus vielen Anfragen besteht (etwa eine Vertonung: Hören, Übersetzen, Sprechen;
    Kopf X-Leitstelle-Arbeit). Ab der zweiten Anfrage gilt sie als begonnen: Modelle, die sie in der Frist genutzt hat,
    entlädt die Leitstelle nicht für andere (Nutzer 18.10.2026: "Begonnenes nicht wegnehmen")."""

    kennung: str                      # Anwendung und Kennung der App, "anwendung:arbeit"
    anwendung: str
    titel: str
    beginn_s: float
    anfragen: int = 0
    modelle: dict[str, float] = Field(default_factory=dict)   # Modellkennung -> letzte Nutzung (Ende der Anfrage)


class Regelwerk(BaseModel):
    """Alles Einstellbare an einem Ort; jede Grenze sichtbar und erklärt (Oberfläche: Regeln)."""

    budget_reserve_gb: float = 18.0
    schutzgrenze_mrd: float = 10.0
    mindestverweildauer_s: float = 600.0
    leerlauf_s: float = 1800.0            # ab wann ein Modell als Leerlauf gilt (Anzeige, Doppel auflösen)
    bedarfsfrist_s: float = 60.0          # wartet ein Auftrag auf den Platz, darf ein Modell schon nach dieser Zeit ohne Auftrag weichen
    arbeit_frist_s: float = 300.0         # so lange nach ihrer letzten Nutzung hält eine begonnene Arbeit ein Modell
    arbeit_ab_anfragen: int = 2           # ab so vielen Anfragen gilt eine Arbeit als begonnen (eine einzelne hält nichts)
    gewinnfaktor: float = 2.0
    extern_schwelle_s: float = 120.0
    hintergrund_spaetestens_s: float = 900.0
    hintergrund_bei_angespannt_anhalten: bool = True
    speicher_warnschwelle: float = 0.92   # Anteil belegt, ab dem die Lage angespannt ist
    automatik: Automatik = Automatik.SELBST
    szenarien_an: dict[Massnahmenart, bool] = Field(default_factory=lambda: {a: True for a in Massnahmenart})
    # Schleifenschutz
    max_massnahmen_je_fenster: int = 6
    fenster_s: float = 600.0
    ruhezeit_s: float = 1800.0
    max_umleitungen_je_auftrag: int = 1
    umschichter_takt_s: float = 5.0
    geladene_zuerst: bool = True


class Massnahme(BaseModel):
    kennung: str
    art: Massnahmenart
    zustand: Massnahmenzustand
    regel: str
    zeit_s: float
    grund: str
    gewinn_s: float = 0.0
    aufwand_s: float = 0.0
    schritte: list[str] = Field(default_factory=list)
    auftraege: list[str] = Field(default_factory=list)
    knoten: str | None = None
    modell: str | None = None         # Modellfamilie
    richtung: str | None = None       # laden, entladen, umleiten (Hauptrichtung)
    bewegungen: list[str] = Field(default_factory=list)   # "laden:familie@knoten", "entladen:familie@knoten" für den Flatterschutz


ANFRAGE_FENSTER_S = 60.0              # Grenzen gelten je Minute


class Verbund(BaseModel):
    """Der ganze Zustand, über den der Kern entscheidet."""

    knoten: dict[str, Knoten] = Field(default_factory=dict)
    dienste: dict[str, Dienst] = Field(default_factory=dict)
    modelle: dict[str, Modell] = Field(default_factory=dict)
    anwendungen: dict[str, Anwendung] = Field(default_factory=dict)
    auftraege: dict[str, Auftrag] = Field(default_factory=dict)
    arbeiten: dict[str, Arbeit] = Field(default_factory=dict)
    regelwerk: Regelwerk = Field(default_factory=Regelwerk)
    betriebsmodus: Betriebsmodus = Betriebsmodus.NORMAL
    hintergrund_an: bool = True       # Regel "Hintergrund bei Lage" (mit Fairness: nach der Frist rückt Hintergrund trotzdem auf)
    hintergrund_erlaubt: bool = True  # Schalter am Hauptregler: aus heißt ohne Ausnahme angehalten
    hintergrund_knoten_bevorzugt: str | None = None
    zeit_s: float = 0.0
    stunde: int = 12                  # Uhrzeit für Zeitfenster
    massnahmen: list[Massnahme] = Field(default_factory=list)
    ereignisse: list[str] = Field(default_factory=list)

    # ── Nachschlagen ─────────────────────────────────────────────────────
    def dienste_auf(self, knoten: str) -> list[Dienst]:
        return [d for d in self.dienste.values() if d.knoten == knoten]

    def modelle_auf(self, knoten: str) -> list[Modell]:
        dienste = {d.kennung for d in self.dienste_auf(knoten)}
        return [m for m in self.modelle.values() if m.dienst in dienste]

    def modelle_von(self, dienst: str) -> list[Modell]:
        return [m for m in self.modelle.values() if m.dienst == dienst]

    def knoten_von_dienst(self, dienst: str) -> Knoten | None:
        k = self.dienste[dienst].knoten
        return self.knoten[k] if k else None

    def geladen_gb(self, knoten: str) -> float:
        """Verplanter Speicher der Modelle im Speicher (Bedarf)."""
        return sum(m.gb for m in self.modelle_auf(knoten) if m.im_speicher)

    def belegt_bekannt_gb(self, knoten: str) -> float:
        """Was die bekannten Modelle gerade wirklich belegen; Grundlage, um den Rest dem System zuzurechnen."""
        return sum(m.belegt_gb for m in self.modelle_auf(knoten) if m.im_speicher)

    def frei_gb(self, knoten: str) -> float:
        k = self.knoten[knoten]
        return k.budget_gb(self.regelwerk.budget_reserve_gb) - self.geladen_gb(knoten)

    def belegt_anteil(self, knoten: str) -> float:
        k = self.knoten[knoten]
        return min(1.0, (k.system_gb + self.geladen_gb(knoten)) / k.speicher_gb) if k.speicher_gb else 0.0

    def offene_auftraege(self) -> list[Auftrag]:
        return [a for a in self.auftraege.values() if a.offen]

    def wartende_auftraege(self) -> list[Auftrag]:
        return [a for a in self.auftraege.values() if a.wartet]

    def laufende_auf_modell(self, modell: str) -> list[Auftrag]:
        return [a for a in self.auftraege.values() if a.zustand == Auftragszustand.LAEUFT and a.modell == modell]

    def plaetze(self, m: Modell) -> int:
        """Gleichzeitige Aufträge auf diesem Modell. Beim Maschinenraum bestimmt seine Dienstdatei die Plätze je Dienst
        (der Eintrag "Dienste auf ..." ist nur ein Behälter); bei anderen Diensten begrenzt ihr Eintrag nach oben, was
        das Modell meldet (etwa `parallel` des Modell-Läufers), damit eine bewusste Begrenzung gilt."""
        d = self.dienste[m.dienst]
        if d.art == "agent":
            return m.plaetze or 1
        return min(d.plaetze, m.plaetze) if m.plaetze else d.plaetze

    def anfrage_gesendet(self, dienst: str, zeit_s: float) -> None:
        """Jede Anfrage an den Dienst (Arbeit, Wiederholung, Zustandsabfrage) zählt für seine Grenze."""
        d = self.dienste.get(dienst)
        if d is not None:
            d.anfragen_s = [t for t in d.anfragen_s if zeit_s - t < ANFRAGE_FENSTER_S] + [zeit_s]

    def anfrage_frei_in_s(self, dienst: str, schon_vergeben: int = 0) -> float:
        """Sekunden, bis der Dienst die nächste Anfrage annimmt (0: jetzt): Sperre nach Überlast und Grenze je Minute. Es
        zählen die gesendeten Anfragen der letzten Minute, zugeteilte, die noch nicht gesendet sind, und `schon_vergeben`
        (in diesem Zuteillauf)."""
        d = self.dienste[dienst]
        warten = max(0.0, (d.gesperrt_bis_s or 0.0) - self.zeit_s)
        if d.anfragen_je_minute:
            fenster = sorted(t for t in d.anfragen_s if self.zeit_s - t < ANFRAGE_FENSTER_S)
            offen = sum(1 for a in self.auftraege.values() if a.dienst == dienst and a.zustand == Auftragszustand.ZUGETEILT) + schon_vergeben
            zuviel = len(fenster) + offen - d.anfragen_je_minute + 1
            if zuviel > 0:
                frei = fenster[zuviel - 1] + ANFRAGE_FENSTER_S - self.zeit_s if zuviel <= len(fenster) else ANFRAGE_FENSTER_S
                warten = max(warten, frei)
        return round(warten, 1)

    def belegung(self, modell: str) -> list[Auftrag]:
        """Aufträge, die das Modell halten: laufende und schon zugeteilte."""
        return [a for a in self.auftraege.values() if a.zustand in (Auftragszustand.LAEUFT, Auftragszustand.ZUGETEILT) and a.modell == modell]

    def instanzen(self, familie: str, knoten: str | None) -> list[Modell]:
        """Alle Instanzen einer Familie auf einem Knoten (Grundinstanz und weitere, auch ladende)."""
        return [m for m in self.modelle.values() if m.familie == familie and self.dienste[m.dienst].knoten == knoten]

    def extern_erlaubt(self, auftrag: Auftrag, modell: Modell) -> bool:
        """Daten verlassen das Heimnetz nur, wenn die Leitstelle der App die Zone extern erlaubt und die App das Modell
        selbst will: ausdrücklich verlangt oder auf ihrer Erlaubnisliste (Nutzer 18.10.2026: "die apps selber entscheiden
        per einstellungen welche dienste sie nutzen wollen")."""
        app = self.anwendungen[auftrag.anwendung]
        return (app.extern_erlaubt and Zone.EXTERN in app.zonen
                and (auftrag.festes_modell == modell.familie or modell.familie in auftrag.extern_familien))

    def arbeit_haelt(self, modell: str, ausser: str | None = None) -> Arbeit | None:
        """Die begonnene Arbeit, die das Modell in der Frist genutzt hat; die fragende Arbeit selbst zählt nicht, sie
        darf eigene Modelle für ihren nächsten Schritt weichen lassen."""
        r = self.regelwerk
        for w in self.arbeiten.values():
            zuletzt = w.modelle.get(modell)
            if w.kennung != ausser and w.anfragen >= r.arbeit_ab_anfragen and zuletzt is not None and self.zeit_s - zuletzt < r.arbeit_frist_s:
                return w
        return None

    def arbeit_zaehlen(self, a: Auftrag, titel: str) -> None:
        """Eine neue Anfrage einer Arbeit."""
        if a.arbeit is None:
            return
        w = self.arbeiten.get(a.arbeit)
        if w is None:
            w = self.arbeiten[a.arbeit] = Arbeit(kennung=a.arbeit, anwendung=a.anwendung, titel=titel, beginn_s=self.zeit_s)
        w.anfragen += 1

    def arbeit_nutzte(self, a: Auftrag) -> None:
        """Ende einer Anfrage: ihr Modell gilt ab jetzt als zuletzt von der Arbeit genutzt."""
        w = self.arbeiten.get(a.arbeit or "")
        if w is not None and a.modell and a.start_s is not None:
            w.modelle[a.modell] = self.zeit_s

    def arbeiten_aufraeumen(self) -> None:
        """Arbeiten ohne offene Anfrage, deren letzte Nutzung länger als die Frist her ist, sind vorbei."""
        offen = {a.arbeit for a in self.auftraege.values() if a.offen and a.arbeit}
        frist = self.regelwerk.arbeit_frist_s
        for k in [k for k, w in self.arbeiten.items() if k not in offen and self.zeit_s - max(w.modelle.values(), default=w.beginn_s) >= frist]:
            del self.arbeiten[k]

    def wartende_auf_familie(self, familie: str) -> list[Auftrag]:
        return [a for a in self.wartende_auftraege() if a.festes_modell == familie or self.erste_familie(a) == familie]

    def erste_familie(self, auftrag: Auftrag) -> str | None:
        kette = self.kette(auftrag)
        return kette[0] if kette else None

    def kette(self, auftrag: Auftrag) -> list[str]:
        if auftrag.festes_modell:
            return [auftrag.festes_modell]
        return list(self.anwendungen[auftrag.anwendung].ketten.get(auftrag.faehigkeit, []))

    def melden(self, text: str) -> None:
        self.ereignisse.append(f"{self.zeit_s:08.1f} {text}")
