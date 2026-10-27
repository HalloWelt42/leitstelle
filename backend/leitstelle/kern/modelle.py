"""Fachmodell der Leitstelle: Knoten, Dienste, Modelle, Anwendungen, Aufträge, Regelwerk, Maßnahmen.

Alles Pydantic, nichts als rohes Dict. Der Verbund ist das Aggregat, über das Zuteiler,
Speicherplaner und Umschichter arbeiten. Zeiten sind Sekunden seit Start (float), damit der
Kern ohne echte Uhr läuft und im Schein-Verbund deterministisch bleibt.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .fenster import Bedarf, Frei, Gesendet, Nutzung, Tokenbuchung, aufraeumen, frei_in_s, im_fenster, nutzung, zahl
from .regelwerk import Regelwerk
from .werte import (
    IM_SPEICHER,
    OFFENE_ZUSTAENDE,
    WARTENDE_ZUSTAENDE,
    Auftragszustand,
    Betriebsmodus,
    Dienstzustand,
    Faehigkeit,
    Hintergrundstufe,
    Knotenzustand,
    Laeuferrolle,
    Massnahmenart,
    Massnahmenzustand,
    Modellzustand,
    Prioritaet,
    Zone,
)


class Prozesslast(BaseModel):
    """Ein Prozess des Modell-Läufers eines Rechners (knoten.last), so weit die Regeln ihn brauchen (ZUSAMMENSPIEL Z6)."""

    pid: int
    name: str
    rolle: Laeuferrolle
    modelldatei: str = ""
    gb: float | None = None
    cpu_prozent: float | None = None  # letzte Messung, Prozent eines Kerns; leer bei der ersten Messung eines Prozesses
    ueber_seit_s: float | None = None # erste Messung der ununterbrochenen Reihe bis jetzt mit mindestens laeufer_schwelle_prozent
    beenden_s: float | None = None    # seit dann lässt die Leitstelle ihn beenden (Regel oder von Hand); er löst nicht erneut aus


class Appteillast(BaseModel):
    """Ein laufender nativer Teil einer App des Stellwerks (knoten.last), vom Stellwerk gestartet, kein KI-Dienst."""

    app: str
    app_name: str
    teil: str
    name: str
    pids: list[int] = Field(default_factory=list)
    cpu_prozent: float | None = None  # Prozent eines Kerns; leer bei der ersten Messung
    gb: float | None = None


class Appslast(BaseModel):
    """Die Apps des Stellwerks auf einem Rechner, wie sein Maschinenraum sie meldet. Ohne `gemessen` sagt `teile`
    nichts; `meldung` sagt, warum (Stellwerk antwortet nicht, ältere Fassung ohne Prozessnummern)."""

    gemessen: bool
    meldung: str = ""
    teile: list[Appteillast] = Field(default_factory=list)

    @property
    def gb(self) -> float:
        return sum(t.gb or 0.0 for t in self.teile)


class Containerlast(BaseModel):
    """Ein laufender Container im Docker-Rechner eines Rechners."""

    name: str
    projekt: str = ""                 # Compose-Projekt; leer: ohne Compose gestartet
    cpu_prozent: float | None = None  # Prozent eines Kerns des Docker-Rechners
    gb: float | None = None


class Dockerlast(BaseModel):
    """Der Docker-Rechner eines Rechners (die virtuelle Maschine der Container). Ohne `gemessen` sagt der Rest nichts."""

    gemessen: bool
    kerne: int | None = None
    speicher_gb: float | None = None
    container: list[Containerlast] = Field(default_factory=list)


class Rechnerlast(BaseModel):
    """Was der Maschinenraum eines Rechners über die Last meldet (knoten.last), mit Verlauf (ZUSAMMENSPIEL Z6). Zwei
    Maße im Fenster der Frist: die Fremdlast (ohne Läufer, Dienste des Maschinenraums, Apps des Stellwerks und ohne die
    Container des Docker-Rechners, Anteil aller Kerne) und die Docker-Last (Container ohne die von Anwendungen mit
    Hintergrundarbeit, Anteil des Docker-Rechners)."""

    zeit_s: float                     # letzte Meldung
    gemessen: bool                    # falsch: die Liste der Läufer-Prozesse sagt nichts (kein lsof, kein Läufer)
    kerne: int
    prozesse: list[Prozesslast] = Field(default_factory=list)
    fremd: list[tuple[float, float]] = Field(default_factory=list)   # (Zeit, Fremdlast in Prozent) je Messung im Fenster, älteste zuerst
    apps: Appslast | None = None      # None: der Maschinenraum meldet keine Apps (kein Stellwerk eingetragen, ältere Fassung)
    docker: Dockerlast | None = None  # None: der Maschinenraum meldet keinen Docker-Rechner (abgeschaltet, ältere Fassung)
    docker_last: list[tuple[float, float]] = Field(default_factory=list)   # (Zeit, Docker-Last in Prozent) je Messung im Fenster

    def fremd_mittel(self, jetzt_s: float, frist_s: float) -> float | None:
        """Gleitendes Mittel der Fremdlast über die Frist; None ohne Messung darin."""
        return _mittel(self.fremd, jetzt_s, frist_s)

    def docker_mittel(self, jetzt_s: float, frist_s: float) -> float | None:
        """Gleitendes Mittel der Docker-Last über die Frist; None ohne Messung darin."""
        return _mittel(self.docker_last, jetzt_s, frist_s)


def _mittel(reihe: list[tuple[float, float]], jetzt_s: float, frist_s: float) -> float | None:
    werte = [w for t, w in reihe if jetzt_s - t <= frist_s]
    return sum(werte) / len(werte) if werte else None


class Knoten(BaseModel):
    kennung: str
    name: str
    zone: Zone
    speicher_gb: float
    system_gb: float = 6.0            # was System und andere Programme belegen (Messwert des Agenten)
    erreichbar: bool = True           # bleibt falsch, solange er schläft: alle Filter gelten unverändert
    schlaeft_seit_s: float | None = None                 # hat sich schlafen gelegt (knoten.schlaeft); None: wach
    hintergrund_fenster: tuple[int, int] | None = None   # Stunden (von, bis), in denen Hintergrundarbeit hierher darf
    budget_fest_gb: float | None = None                  # von Hand gesetztes Budget; sonst Gesamtspeicher minus Reserve
    last: Rechnerlast | None = None                      # knoten.last seines Maschinenraums; None: keine Meldung (keiner, ältere Fassung)
    laeufer_umgehungen: list[str] = Field(default_factory=list)   # wer den Läufer am Leitstand vorbei anspricht (nach der Deutung)
    hintergrund_stufe: Hintergrundstufe = Hintergrundstufe.FREI   # Regel "Hintergrund bei Rechnerlast"
    hintergrund_grund: str = ""
    hintergrund_seit_s: float | None = None

    @property
    def schlaeft(self) -> bool:
        return self.schlaeft_seit_s is not None

    @property
    def zustand(self) -> Knotenzustand:
        if self.schlaeft:
            return Knotenzustand.SCHLAEFT
        return Knotenzustand.ERREICHBAR if self.erreichbar else Knotenzustand.NICHT_ERREICHBAR

    def budget_gb(self, reserve_gb: float) -> float:
        """Speicher, den Modelle zusammen höchstens belegen dürfen."""
        if self.budget_fest_gb is not None:
            return max(0.0, min(self.budget_fest_gb, self.speicher_gb - self.system_gb))
        return max(0.0, self.speicher_gb - max(reserve_gb, self.system_gb))


ART_MASCHINENRAUM = "agent"          # Adapterart der Dienste, die ein Maschinenraum startet und anhält


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
    anfragen_je_minute: int | None = None   # Grenzen des Anbieters je Minute (gleitend, je Schlüssel); die Leitstelle hält sie ein
    token_ein_je_minute: int | None = None
    token_aus_je_minute: int | None = None
    gesendet: list[Gesendet] = Field(default_factory=list)       # gesendete Anfragen im gleitenden Fenster (kern/fenster.py)
    token: list[Tokenbuchung] = Field(default_factory=list)      # Token je Anfrage, geschätzt oder echt
    gesperrt_bis_s: float | None = None     # nach Überlast des Dienstes (429, extern auch 5xx)
    einbettung_instanzen: int = 1           # so viele Instanzen je Einbettungsmodell darf die Leitstelle laden (Modell-Läufer)
    einbettung_spielraum_gb: float = 4.0    # so viel bleibt im Budget des Rechners frei, wenn sie Einbettungsinstanzen lädt

    @property
    def nutzbar(self) -> bool:
        return self.zustand == Dienstzustand.BEREIT

    @property
    def maschinenraum(self) -> bool:
        """Programme im Maschinenraum eines Rechners: Laden heißt Starten, Entladen heißt Anhalten."""
        return self.art == ART_MASCHINENRAUM


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
        if self.zusatz:
            return False                  # eine weitere Instanz hat die Leitstelle selbst gestartet; sie weicht zuerst
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
    docker_projekte: list[str] = Field(default_factory=list)   # ihre Container im Docker-Rechner: Compose-Projekte oder Containernamen


class Auftrag(BaseModel):
    kennung: str
    anwendung: str
    faehigkeit: Faehigkeit
    prioritaet: Prioritaet
    eingang_s: float
    zustand: Auftragszustand = Auftragszustand.EINGEREIHT
    festes_modell: str | None = None  # Familie, wenn die Anwendung ein Modell verlangt
    alternativen: list[str] = Field(default_factory=list)   # Familien, die die Anwendung dazu nennt, in ihrer Reihenfolge: nur, wenn das verlangte nicht geht
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
    schlafende_knoten: list[str] = Field(default_factory=list)   # abgelehnt, weil diese Rechner schlafen (rechner_schlaeft)
    voraussichtlich_s: float | None = None
    teilergebnis: bool = False
    grund: str | None = None          # Wort aus PROTOKOLL.md Abschnitt 7, wenn abgelehnt oder abgebrochen
    arbeit: str | None = None         # Arbeit der Anwendung, zu der die Anfrage gehört (Kopf X-Leitstelle-Arbeit)
    extern_familien: list[str] = Field(default_factory=list)   # Erlaubnisliste der App für externe Modelle (Kopf X-Leitstelle-Extern)
    feste_instanz: str | None = None  # Folgeaufruf an genau diese Modellinstanz (Kopf X-Leitstelle-Instanz)
    token_ein_geschaetzt: int = 0     # aus der Länge der Anfrage, für die Grenzen je Minute; nach der Antwort zählt der echte Verbrauch
    token_aus_geschaetzt: int = 0     # höchstens so viele verlangt die Anfrage (max_tokens); 0: nicht bekannt

    @property
    def bedarf(self) -> Bedarf:
        """Was der Auftrag von den Grenzen seines Dienstes je Minute braucht: eine Anfrage und seine Token."""
        return Bedarf(anfragen=1, token_ein=self.token_ein_geschaetzt, token_aus=self.token_aus_geschaetzt)

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

    def auf_schlafendem(self, dienst: str) -> bool:
        """Liegt der Dienst auf einem Rechner, der schläft? Externe Anbieter schlafen nie."""
        d = self.dienste.get(dienst)
        k = self.knoten.get(d.knoten) if d and d.knoten else None
        return k is not None and k.schlaeft

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
        if d.maschinenraum:
            return m.plaetze or 1
        return min(d.plaetze, m.plaetze) if m.plaetze else d.plaetze

    # ── Grenzen je Minute (kern/fenster.py) ──────────────────────────────
    def anfrage_gesendet(self, dienst: str, zeit_s: float, familie: str | None = None) -> None:
        """Jede Anfrage an den Dienst (Arbeit, Wiederholung, Zustandsabfrage) zählt für seine Grenze, mit dem Modell, das sie nennt."""
        d = self.dienste.get(dienst)
        if d is not None:
            d.gesendet, d.token = aufraeumen(d.gesendet, d.token, zeit_s)
            d.gesendet.append(Gesendet(zeit_s=zeit_s, familie=familie))

    def token_vorbuchen(self, dienst: str, kennung: str, familie: str | None, ein: int, aus: int, zeit_s: float) -> None:
        """Vor dem Senden: die geschätzten Token zählen sofort (eine neue Buchung derselben Kennung ersetzt die alte)."""
        d = self.dienste.get(dienst)
        if d is not None:
            d.gesendet, d.token = aufraeumen(d.gesendet, d.token, zeit_s)
            d.token = [t for t in d.token if t.kennung != kennung] + [Tokenbuchung(kennung=kennung, familie=familie, zeit_s=zeit_s, ende_s=zeit_s,
                                                                                        token_ein=ein, token_aus=aus)]

    def token_abschliessen(self, dienst: str, kennung: str, zeit_s: float, ein: int | None = None, aus: int | None = None) -> None:
        """Nach der Antwort: der echte Verbrauch ersetzt die Schätzung (fehlt er, bleibt die Schätzung); Token heraus zählen
        ab jetzt."""
        d = self.dienste.get(dienst)
        for t in d.token if d is not None else []:
            if t.kennung == kennung and t.offen:
                t.token_ein = t.token_ein if ein is None else ein
                t.token_aus = t.token_aus if aus is None else aus
                t.ende_s, t.offen = zeit_s, False

    def token_streichen(self, dienst: str, kennung: str) -> None:
        """Der Anbieter hat die Anfrage mit Überlast abgelehnt: sie hat keine Token verbraucht."""
        d = self.dienste.get(dienst)
        if d is not None:
            d.token = [t for t in d.token if not (t.kennung == kennung and t.offen)]

    def nutzung(self, dienst: str, familie: str | None = None) -> Nutzung:
        """Anfragen und Token im gleitenden Fenster, für den ganzen Dienst (Schlüssel) oder ein Modell."""
        d = self.dienste[dienst]
        return nutzung(d.gesendet, d.token, self.zeit_s, familie)

    def frei(self, dienst: str, dazu: Bedarf | None = None) -> Frei:
        """Wann der Dienst Anfragen mit dem Bedarf `dazu` annimmt (Vorgabe: eine Anfrage) und welche Grenze bindet: Sperre
        nach Überlast, Anfragen, Token hinein und heraus je Minute. Es zählen das Fenster, zugeteilte und noch nicht gesendete
        Aufträge und `dazu` (in diesem Zuteillauf vergeben und die neue Anfrage)."""
        d = self.dienste[dienst]
        dazu = dazu if dazu is not None else Bedarf(anfragen=1)
        offen = sum((a.bedarf for a in self.auftraege.values() if a.dienst == dienst and a.zustand == Auftragszustand.ZUGETEILT), Bedarf()) + dazu
        jetzt = self.zeit_s
        kandidaten = [Frei(in_s=max(0.0, (d.gesperrt_bis_s or 0.0) - jetzt), grund="Dienst meldete Überlast")]
        if d.anfragen_je_minute:
            kandidaten.append(Frei(in_s=frei_in_s([(g.zeit_s, 1) for g in d.gesendet if im_fenster(g.zeit_s, jetzt)], offen.anfragen, d.anfragen_je_minute, jetzt),
                                   grund=f"Grenze von {zahl(d.anfragen_je_minute)} Anfragen je Minute erreicht"))
        if d.token_ein_je_minute:
            kandidaten.append(Frei(in_s=frei_in_s([(t.zeit_s, t.token_ein) for t in d.token if im_fenster(t.zeit_s, jetzt)], offen.token_ein,
                                                  d.token_ein_je_minute, jetzt),
                                   grund=f"Grenze von {zahl(d.token_ein_je_minute)} Token hinein je Minute erreicht"))
        if d.token_aus_je_minute:
            kandidaten.append(Frei(in_s=frei_in_s([(t.ende_s, t.token_aus) for t in d.token if im_fenster(t.ende_s, jetzt)], offen.token_aus,
                                                  d.token_aus_je_minute, jetzt),
                                   grund=f"Grenze von {zahl(d.token_aus_je_minute)} Token heraus je Minute erreicht"))
        engpass = max(kandidaten, key=lambda f: f.in_s)
        return Frei(in_s=round(engpass.in_s, 1), grund=engpass.grund if engpass.in_s > 0 else "")

    def anfrage_frei_in_s(self, dienst: str, dazu: Bedarf | None = None) -> float:
        """Sekunden, bis der Dienst Anfragen mit diesem Bedarf annimmt (0: jetzt); siehe `frei`."""
        return self.frei(dienst, dazu).in_s

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
                and (self.verlangt(auftrag, modell.familie) or modell.familie in auftrag.extern_familien))

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
        """Welche Modelle in Frage kommen, immer die Wahl der Anwendung: das verlangte Modell mit den Alternativen, die sie
        dazu nennt, sonst ihre Kette in der Leitstelle. Die Leitstelle wählt daraus nur Quelle (Rechner, Instanz) und
        Zeitpunkt, nie ein Modell, das die Anwendung nicht genannt hat."""
        if auftrag.festes_modell:
            return [auftrag.festes_modell, *auftrag.alternativen]
        return list(self.anwendungen[auftrag.anwendung].ketten.get(auftrag.faehigkeit, []))

    @staticmethod
    def verlangt(auftrag: Auftrag, familie: str) -> bool:
        """Hat die Anwendung dieses Modell selbst genannt (als `model` oder als Alternative)?"""
        return familie == auftrag.festes_modell or familie in auftrag.alternativen

    def melden(self, text: str) -> None:
        self.ereignisse.append(f"{self.zeit_s:08.1f} {text}")
