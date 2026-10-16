"""Lagebild: alles, was die Oberfläche live zeigt, in einem Stück. Schlüssel statt Wörter; die
Oberfläche übersetzt (eine Wortliste dort). Geheimnisse kommen hier nie vor."""

from __future__ import annotations

from pydantic import BaseModel

from .. import version
from ..kern.modelle import Massnahme
from ..kern.werte import Auftragszustand, Automatik, Betriebsmodus, Dienstzustand, Faehigkeit, Lage, Modellzustand, Zone
from ..ports.ablage.eintraege import Schritt
from ..protokoll.knoten import Messwerte
from .betrieb import Betrieb


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
    erreichbar: bool
    budget_fest_gb: float | None
    hintergrund_von: int | None
    hintergrund_bis: int | None
    agent: AgentSicht


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
                                  budget_fest_gb=k.budget_fest_gb, hintergrund_von=e.hintergrund_von, hintergrund_bis=e.hintergrund_bis, agent=agent))
    dienste = [DienstSicht(kennung=d.kennung, name=d.name, art=d.art.value, adresse=d.adresse, knoten=d.knoten, extern=d.extern,
                           zustand=v.dienste[d.kennung].zustand if d.kennung in v.dienste else Dienstzustand.NICHT_ERREICHBAR,
                           steuerbar=b.steuerbar.get(d.kennung, False), meldung=b.dienst_meldung.get(d.kennung, ""), plaetze=d.plaetze,
                           zugang=d.zugang_geheim is not None) for d in b.dienste.values()]
    modelle = [ModellSicht(kennung=m.kennung, name=m.name, familie=m.familie, dienst=m.dienst, knoten=v.dienste[m.dienst].knoten if m.dienst in v.dienste else None,
                           faehigkeiten=sorted(m.faehigkeiten, key=lambda f: f.value), gb=m.gb, gb_jetzt=m.gb_jetzt, parameter_mrd=m.parameter_mrd, zustand=m.zustand,
                           geschuetzt=m.geschuetzt(r.schutzgrenze_mrd), geladen_seit_s=m.geladen_seit_s, letzte_nutzung_s=m.letzte_nutzung_s,
                           auftraege_aktiv=m.auftraege_aktiv, ladesperre_bis_s=m.ladesperre_bis_s, ladesperre_grund=m.ladesperre_grund)
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
                    hintergrund_an=v.hintergrund_an, lage=b.kern.lage, lage_grund=b.kern.lage_grund, automatik=r.automatik,
                    knoten=knoten, dienste=dienste, modelle=modelle, auftraege=auftraege, anwendungen=anwendungen,
                    massnahmen=list(b.massnahmen)[:20], meldungen=[Meldung(zeit_s=z, text=t) for z, t in list(b.meldungen)[:30]])
