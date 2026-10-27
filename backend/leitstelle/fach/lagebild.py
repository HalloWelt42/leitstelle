"""Lagebild: alles, was die Oberfläche live zeigt, in einem Stück. Schlüssel statt Wörter; die
Oberfläche übersetzt (eine Wortliste dort). Geheimnisse kommen hier nie vor."""

from __future__ import annotations

from pydantic import BaseModel

from .. import version
from ..kern.modelle import ANFRAGE_FENSTER_S, Knoten, Massnahme, Regelwerk, Verbund
from ..kern.rechnerlast import fremd_mittel, laeuferarbeit, ohne_auftrag_seit
from ..protokoll.steckbrief import Steckbrief
from ..kern.werte import (Auftragszustand, Automatik, Betriebsmodus, Dienstzustand, Faehigkeit, Hintergrundstufe, Knotenzustand, Laeuferrolle, Lage,
                          Modellzustand, Zone)
from ..ports.ablage.eintraege import Schritt
from ..protokoll.knoten import Fremdzugriff, Fremdzugriffe, Messwerte
from .betrieb import Betrieb
from .umgehungen import Fremddeutung, deuten


class AgentSicht(BaseModel):
    """Knoten-Agent: Schlüssel vergeben, verbunden, und was er zuletzt gemessen hat."""

    schluessel: bool
    verbunden: bool
    seit_s: float | None
    betriebssystem: str | None
    version: str | None
    messwege: list[str]
    messzeit_s: float | None
    messwerte: Messwerte | None


class FremdzugriffSicht(Fremdzugriff):
    """Ein Zugriff am Leitstand vorbei, wie der Maschinenraum ihn meldet, mit der Deutung der Leitstelle."""

    deutung: Fremddeutung


class FremdeSicht(BaseModel):
    """Am Leitstand vorbei (`knoten.fremde`): ohne verbundenen Maschinenraum oder ohne seine Beobachtung nicht beobachtet."""

    beobachtet: bool
    zugriffe: list[FremdzugriffSicht]
    umgehungen: int                    # echte Umgehungen: alle Zugriffe ohne die Leitstelle selbst auf dem direkten Weg


def fremde_sicht(f: Fremdzugriffe, laeufer_direkt: bool) -> FremdeSicht:
    zugriffe = [FremdzugriffSicht(**z.model_dump(), deutung=deuten(z, laeufer_direkt)) for z in f.zugriffe] if f.beobachtet else []
    return FremdeSicht(beobachtet=f.beobachtet, zugriffe=zugriffe,
                       umgehungen=sum(1 for z in zugriffe if z.deutung != Fremddeutung.LEITSTELLE_DIREKT))


class LaeuferprozessSicht(BaseModel):
    """Ein Prozess des Modell-Läufers, wie der Maschinenraum ihn misst, mit dem Befund der Leitstelle."""

    pid: int
    name: str
    rolle: Laeuferrolle
    modelldatei: str
    cpu_prozent: float | None          # Prozent eines Kerns (100 heißt ein Kern)
    gb: float | None
    ohne_auftrag_seit_s: float | None  # rechnet seitdem über der Schwelle ohne Auftrag der Leitstelle (nur ab der Frist gesetzt)
    beenden_s: float | None            # die Leitstelle lässt ihn gerade beenden


class LastSicht(BaseModel):
    """Last von Läufer und Rechner (`knoten.last`) und was die Leitstelle daraus macht (ZUSAMMENSPIEL Z6)."""

    gemeldet: bool                     # der Maschinenraum meldet die Last (ab Fassung 0.15)
    gemessen: bool                     # die Liste der Läufer-Prozesse sagt etwas (lsof da, Läufer eingetragen)
    kerne: int | None
    fremd_prozent: float | None        # letzte Messung, Anteil aller Kerne
    fremd_mittel_prozent: float | None # gleitendes Mittel über last_frist_s; danach richtet sich die Stufe
    laeufer: list[LaeuferprozessSicht]
    auftraege: int                     # Aufträge der Leitstelle, die gerade auf dem Läufer laufen oder ihm zugeteilt sind
    zuletzt_s: float | None            # wann zuletzt ein Auftrag der Leitstelle auf dem Läufer lief
    umgehungen: list[str]              # wer den Läufer am Leitstand vorbei anspricht (Erklärung für Rechnen ohne Auftrag)
    stufe: Hintergrundstufe            # Hintergrund auf diesem Rechner: frei, gedrosselt, angehalten
    stufe_grund: str
    stufe_seit_s: float | None


def last_sicht(v: Verbund, k: Knoten) -> LastSicht:
    last = k.last
    frist = v.regelwerk.laeufer_frist_s
    laeufer = []
    for p in last.prozesse if last else []:
        seit = ohne_auftrag_seit(v, k.kennung, p)
        laeufer.append(LaeuferprozessSicht(pid=p.pid, name=p.name, rolle=p.rolle, modelldatei=p.modelldatei, cpu_prozent=p.cpu_prozent, gb=p.gb,
                                           ohne_auftrag_seit_s=seit if seit is not None and v.zeit_s - seit >= frist else None,
                                           beenden_s=p.beenden_s))
    arbeit = laeuferarbeit(v, k.kennung)
    mittel = fremd_mittel(v, k)
    return LastSicht(gemeldet=last is not None, gemessen=bool(last and last.gemessen), kerne=last.kerne if last else None,
                     fremd_prozent=last.fremd[-1][1] if last and last.fremd else None,
                     fremd_mittel_prozent=round(mittel, 1) if mittel is not None else None, laeufer=laeufer,
                     auftraege=arbeit.auftraege, zuletzt_s=arbeit.zuletzt_s, umgehungen=list(k.laeufer_umgehungen),
                     stufe=k.hintergrund_stufe, stufe_grund=k.hintergrund_grund, stufe_seit_s=k.hintergrund_seit_s)


class KnotenSicht(BaseModel):
    kennung: str
    name: str
    adresse: str
    zone: Zone
    speicher_gb: float
    system_gb: float
    budget_gb: float
    geladen_gb: float
    frei_gb: float
    belegt_anteil: float
    erreichbar: bool                   # falsch auch, solange er schläft
    zustand: Knotenzustand             # erreichbar, nicht erreichbar oder schläft (kein Ausfall)
    schlaeft_seit_s: float | None
    budget_fest_gb: float | None
    hintergrund_von: int | None
    hintergrund_bis: int | None
    agent: AgentSicht
    fremde: FremdeSicht                # was am Leitstand vorbei auf Modelle dieses Rechners zugreift
    last: LastSicht                    # Last von Läufer und Rechner, Stufe des Hintergrunds


class DienstSicht(BaseModel):
    kennung: str
    name: str
    art: str
    adresse: str
    knoten: str | None
    extern: bool
    zustand: Dienstzustand
    steuerbar: bool
    meldung: str
    plaetze: int
    zugang: bool
    anfragen_je_minute: int | None     # Grenze des Anbieters
    anfragen_letzte_minute: int        # gesendete Anfragen im Fenster
    frei_in_s: float                   # bis zur nächsten erlaubten Anfrage (0: jetzt)
    fehlschlaege: int                  # Prüfungen ohne Antwort in Folge
    naechste_pruefung_s: float | None  # Zeitpunkt der nächsten Zustandsabfrage (None: meldet sich selbst)
    einbettung_instanzen: int          # Instanzen je Einbettungsmodell bei Andrang (1: keine weiteren)
    einbettung_spielraum_gb: float     # bleibt im Budget des Rechners frei
    ueber_maschinenraum: bool          # Modell-Läufer: Weg über den Maschinenraum seines Rechners statt direkt an die Adresse


class ModellSicht(BaseModel):
    kennung: str
    name: str
    familie: str
    dienst: str
    knoten: str | None
    faehigkeiten: list[Faehigkeit]
    gb: float
    gb_jetzt: float | None
    parameter_mrd: float
    zustand: Modellzustand
    geschuetzt: bool
    geladen_seit_s: float | None
    letzte_nutzung_s: float | None
    auftraege_aktiv: int
    plaetze: int
    gehalten_von: str | None          # Titel der begonnenen Arbeit, für die es nicht weicht
    steckbrief: Steckbrief             # wofür es gemacht ist, was es kann, wie es sich verhält (PROTOKOLL 4.8)
    instanzen_hoechstens: int          # so viele Instanzen darf die Leitstelle starten
    zusatz: bool                       # weitere Instanz: weicht bei Speichermangel zuerst
    ladesperre_bis_s: float | None
    ladesperre_grund: str


class AuftragSicht(BaseModel):
    kennung: str
    anwendung: str
    faehigkeit: Faehigkeit
    prioritaet: int
    titel: str
    zustand: Auftragszustand
    begruendung: str
    modell: str | None
    familie_wunsch: str | None
    dienst: str | None
    knoten: str | None
    extern: bool
    eingang_s: float
    start_s: float | None
    voraussichtlich_s: float | None
    umgeleitet: int
    auslaufend: bool
    schritte: list[Schritt]


class AnwendungSicht(BaseModel):
    kennung: str
    name: str
    prioritaet: int
    faehigkeiten: list[Faehigkeit]
    zonen: list[Zone]
    extern_erlaubt: bool
    gleichzeitig: int
    ketten: dict[str, list[str]]
    gesperrt: bool
    sperrgrund: str
    angelegt_s: float


class Meldung(BaseModel):
    zeit_s: float
    text: str


class Lagebild(BaseModel):
    version: str
    zeit_s: float
    modus: Betriebsmodus
    hintergrund_erlaubt: bool
    hintergrund_an: bool
    lage: Lage
    lage_grund: str
    automatik: Automatik
    regelwerk: Regelwerk               # alle Regelwerte, zur Anzeige und Erklärung neben dem, worauf sie wirken
    knoten: list[KnotenSicht]
    dienste: list[DienstSicht]
    modelle: list[ModellSicht]
    auftraege: list[AuftragSicht]
    anwendungen: list[AnwendungSicht]
    massnahmen: list[Massnahme]
    meldungen: list[Meldung]


def lagebild(b: Betrieb) -> Lagebild:
    v = b.verbund
    r = v.regelwerk
    knoten = []
    for k in v.knoten.values():
        e = b.knoten[k.kennung]
        av = b.agenten.verbindung(k.kennung)
        agent = AgentSicht(schluessel=e.agent_fingerabdruck is not None, verbunden=av is not None, seit_s=av.seit_s if av else None,
                           betriebssystem=av.anmeldung.betriebssystem if av else None, version=av.anmeldung.agent_version if av else None,
                           messwege=list(av.anmeldung.messwege) if av else [], messzeit_s=av.messzeit_s if av else None,
                           messwerte=av.messwerte if av else None)
        knoten.append(KnotenSicht(kennung=k.kennung, name=k.name, adresse=e.adresse, zone=k.zone, speicher_gb=k.speicher_gb, system_gb=k.system_gb,
                                  budget_gb=round(k.budget_gb(r.budget_reserve_gb), 2), geladen_gb=round(v.geladen_gb(k.kennung), 2),
                                  frei_gb=round(v.frei_gb(k.kennung), 2), belegt_anteil=round(v.belegt_anteil(k.kennung), 3), erreichbar=k.erreichbar,
                                  zustand=k.zustand, schlaeft_seit_s=k.schlaeft_seit_s, budget_fest_gb=k.budget_fest_gb, hintergrund_von=e.hintergrund_von, hintergrund_bis=e.hintergrund_bis, agent=agent,
                                  fremde=fremde_sicht(av.fremde if av else Fremdzugriffe(beobachtet=False), b.laeufer_direkt(k.kennung)),
                                  last=last_sicht(v, k)))
    dienste = [DienstSicht(kennung=d.kennung, name=d.name, art=d.art.value, adresse=d.adresse, knoten=d.knoten, extern=d.extern,
                           zustand=v.dienste[d.kennung].zustand if d.kennung in v.dienste else Dienstzustand.NICHT_ERREICHBAR,
                           steuerbar=b.steuerbar.get(d.kennung, False), meldung=b.dienst_meldung.get(d.kennung, ""), plaetze=d.plaetze,
                           zugang=d.zugang_geheim is not None, anfragen_je_minute=d.anfragen_je_minute,
                           anfragen_letzte_minute=sum(1 for t in v.dienste[d.kennung].anfragen_s if v.zeit_s - t < ANFRAGE_FENSTER_S) if d.kennung in v.dienste else 0,
                           frei_in_s=v.anfrage_frei_in_s(d.kennung) if d.kennung in v.dienste else 0.0,
                           fehlschlaege=b.pruefstand[d.kennung].fehlschlaege if d.kennung in b.pruefstand else 0,
                           naechste_pruefung_s=None if d.kennung in b.adapter and b.adapter[d.kennung].meldet_sich_selbst
                           else b.pruefstand[d.kennung].naechste_s if d.kennung in b.pruefstand else None,
                           einbettung_instanzen=d.einbettung_instanzen, einbettung_spielraum_gb=d.einbettung_spielraum_gb,
                           ueber_maschinenraum=d.ueber_maschinenraum) for d in b.dienste.values()]
    modelle = [ModellSicht(kennung=m.kennung, name=m.name, familie=m.familie, dienst=m.dienst, knoten=v.dienste[m.dienst].knoten if m.dienst in v.dienste else None,
                           faehigkeiten=sorted(m.faehigkeiten, key=lambda f: f.value), gb=m.gb, gb_jetzt=m.gb_jetzt, parameter_mrd=m.parameter_mrd, zustand=m.zustand,
                           geschuetzt=m.geschuetzt(r.schutzgrenze_mrd), geladen_seit_s=m.geladen_seit_s, letzte_nutzung_s=m.letzte_nutzung_s,
                           auftraege_aktiv=m.auftraege_aktiv, plaetze=v.plaetze(m),
                           gehalten_von=w.titel if (w := v.arbeit_haelt(m.kennung)) else None, steckbrief=b.steckbrief(m), instanzen_hoechstens=m.instanzen_hoechstens, zusatz=m.zusatz,
                           ladesperre_bis_s=m.ladesperre_bis_s, ladesperre_grund=m.ladesperre_grund)
               for m in sorted(v.modelle.values(), key=lambda x: (x.dienst, -x.gb))]
    auftraege = []
    for a in sorted(v.auftraege.values(), key=lambda x: x.eingang_s):
        lauf = b.laeufe.get(a.kennung)
        m = v.modelle.get(a.modell or "")
        auftraege.append(AuftragSicht(kennung=a.kennung, anwendung=a.anwendung, faehigkeit=a.faehigkeit, prioritaet=int(a.prioritaet),
                                      titel=lauf.titel if lauf else "", zustand=a.zustand, begruendung=a.begruendung, modell=m.name if m else None,
                                      familie_wunsch=a.festes_modell, dienst=a.dienst, knoten=a.knoten, extern=a.extern, eingang_s=a.eingang_s,
                                      start_s=a.start_s, voraussichtlich_s=a.voraussichtlich_s, umgeleitet=a.umgeleitet,
                                      auslaufend=bool(lauf and lauf.danach_sperren), schritte=list(lauf.schritte) if lauf else []))
    anwendungen = [AnwendungSicht(kennung=x.kennung, name=x.name, prioritaet=int(x.prioritaet), faehigkeiten=sorted(x.faehigkeiten, key=lambda f: f.value),
                                  zonen=sorted(x.zonen, key=lambda z: z.value), extern_erlaubt=x.extern_erlaubt, gleichzeitig=x.gleichzeitig,
                                  ketten={f.value: k for f, k in x.ketten.items()}, gesperrt=x.gesperrt, sperrgrund=x.sperrgrund, angelegt_s=x.angelegt_s)
                   for x in b.anwendungen.values()]
    return Lagebild(version=version(), zeit_s=b.uhr.jetzt(), modus=v.betriebsmodus, hintergrund_erlaubt=v.hintergrund_erlaubt,
                    hintergrund_an=v.hintergrund_an, lage=b.kern.lage, lage_grund=b.kern.lage_grund, automatik=r.automatik, regelwerk=r,
                    knoten=knoten, dienste=dienste, modelle=modelle, auftraege=auftraege, anwendungen=anwendungen,
                    massnahmen=list(b.massnahmen)[:20], meldungen=[Meldung(zeit_s=z, text=t) for z, t in list(b.meldungen)[:30]])
