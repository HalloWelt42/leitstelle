"""Repositorien je Aggregat. Niemand spricht an ihnen vorbei mit der Datenbank.

Jede Methode öffnet ihre eigene kurze Sitzung; gelesen wird vollständig, bevor geschrieben wird.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select

from ...kern.messungen import Messwerk, Mittel
from ...kern.modelle import Massnahme, Regelwerk
from ...kern.werte import Auftragszustand, Faehigkeit, Massnahmenart, Massnahmenzustand, OFFENE_ZUSTAENDE, Prioritaet, Zone
from .datenbank import Datenbank
from .eintraege import AliasEintrag, AnwendungEintrag, AuftragEintrag, BetriebEinstellung, DienstEintrag, Kennzahlen, KnotenEintrag, PruefEintrag
from .tabellen import (
    AliasTabelle,
    AnwendungTabelle,
    AuftragTabelle,
    DienstTabelle,
    EinstellungTabelle,
    KnotenTabelle,
    MassnahmeTabelle,
    MessungTabelle,
    PruefTabelle,
)


def _felder(zeile, *namen: str) -> dict:
    return {n: getattr(zeile, n) for n in namen}


class KnotenAblage:
    FELDER = ("kennung", "name", "adresse", "zone", "speicher_gb", "system_gb", "budget_fest_gb", "hintergrund_von", "hintergrund_bis",
              "agent_fingerabdruck", "agent_geheim")

    def __init__(self, db: Datenbank) -> None:
        self.db = db

    async def alle(self) -> list[KnotenEintrag]:
        async with self.db.sitzung() as s:
            zeilen = (await s.scalars(select(KnotenTabelle).order_by(KnotenTabelle.name))).all()
            return [KnotenEintrag(**_felder(z, *self.FELDER)) for z in zeilen]

    async def speichern(self, k: KnotenEintrag) -> None:
        async with self.db.sitzung() as s, s.begin():
            await s.merge(KnotenTabelle(**k.model_dump(mode="json")))

    async def loeschen(self, kennung: str) -> None:
        async with self.db.sitzung() as s, s.begin():
            await s.execute(delete(KnotenTabelle).where(KnotenTabelle.kennung == kennung))


class DienstAblage:
    FELDER = ("kennung", "name", "art", "adresse", "knoten", "extern", "zugang_geheim", "plaetze")

    def __init__(self, db: Datenbank) -> None:
        self.db = db

    async def alle(self) -> list[DienstEintrag]:
        async with self.db.sitzung() as s:
            zeilen = (await s.scalars(select(DienstTabelle).order_by(DienstTabelle.name))).all()
            return [DienstEintrag(**_felder(z, *self.FELDER)) for z in zeilen]

    async def speichern(self, d: DienstEintrag) -> None:
        async with self.db.sitzung() as s, s.begin():
            await s.merge(DienstTabelle(**d.model_dump(mode="json")))

    async def loeschen(self, kennung: str) -> None:
        async with self.db.sitzung() as s, s.begin():
            await s.execute(delete(DienstTabelle).where(DienstTabelle.kennung == kennung))


class AnwendungAblage:
    def __init__(self, db: Datenbank) -> None:
        self.db = db

    @staticmethod
    def _eintrag(z: AnwendungTabelle) -> AnwendungEintrag:
        return AnwendungEintrag(
            kennung=z.kennung, name=z.name, schluessel_fingerabdruck=z.schluessel_fingerabdruck, schluessel_geheim=z.schluessel_geheim,
            prioritaet=Prioritaet(z.prioritaet), faehigkeiten={Faehigkeit(f) for f in z.faehigkeiten}, zonen={Zone(x) for x in z.zonen},
            extern_erlaubt=z.extern_erlaubt, gleichzeitig=z.gleichzeitig, ketten={Faehigkeit(f): list(k) for f, k in z.ketten.items()},
            gesperrt=z.gesperrt, sperrgrund=z.sperrgrund, angelegt_s=z.angelegt_s)

    async def alle(self) -> list[AnwendungEintrag]:
        async with self.db.sitzung() as s:
            return [self._eintrag(z) for z in (await s.scalars(select(AnwendungTabelle).order_by(AnwendungTabelle.name))).all()]

    async def speichern(self, a: AnwendungEintrag) -> None:
        daten = a.model_dump(mode="json")
        daten["prioritaet"] = int(a.prioritaet)
        daten["faehigkeiten"] = sorted(f.value for f in a.faehigkeiten)
        daten["zonen"] = sorted(z.value for z in a.zonen)
        async with self.db.sitzung() as s, s.begin():
            await s.merge(AnwendungTabelle(**daten))

    async def loeschen(self, kennung: str) -> None:
        async with self.db.sitzung() as s, s.begin():
            await s.execute(delete(AnwendungTabelle).where(AnwendungTabelle.kennung == kennung))


class AliasAblage:
    def __init__(self, db: Datenbank) -> None:
        self.db = db

    async def alle(self) -> list[AliasEintrag]:
        async with self.db.sitzung() as s:
            return [AliasEintrag(alias=z.alias, familie=z.familie) for z in (await s.scalars(select(AliasTabelle))).all()]

    async def speichern(self, a: AliasEintrag) -> None:
        async with self.db.sitzung() as s, s.begin():
            await s.merge(AliasTabelle(alias=a.alias, familie=a.familie))

    async def loeschen(self, alias: str) -> None:
        async with self.db.sitzung() as s, s.begin():
            await s.execute(delete(AliasTabelle).where(AliasTabelle.alias == alias))


class AuftragAblage:
    FELDER = tuple(AuftragEintrag.model_fields)

    def __init__(self, db: Datenbank) -> None:
        self.db = db

    @classmethod
    def _eintrag(cls, z: AuftragTabelle) -> AuftragEintrag:
        return AuftragEintrag(**_felder(z, *cls.FELDER))

    async def speichern(self, a: AuftragEintrag) -> None:
        daten = a.model_dump(mode="json")
        daten["prioritaet"] = int(a.prioritaet)
        async with self.db.sitzung() as s, s.begin():
            await s.merge(AuftragTabelle(**daten))

    async def holen(self, kennung: str) -> AuftragEintrag | None:
        async with self.db.sitzung() as s:
            z = await s.get(AuftragTabelle, kennung)
            return self._eintrag(z) if z else None

    async def seite(self, ab: int = 0, anzahl: int = 50, anwendung: str | None = None, zustand: Auftragszustand | None = None) -> tuple[list[AuftragEintrag], int]:
        """Neueste zuerst, seitenweise, mit Gesamtzahl für die Anzeige."""
        bedingung = []
        if anwendung:
            bedingung.append(AuftragTabelle.anwendung == anwendung)
        if zustand:
            bedingung.append(AuftragTabelle.zustand == zustand.value)
        async with self.db.sitzung() as s:
            gesamt = await s.scalar(select(func.count()).select_from(AuftragTabelle).where(*bedingung)) or 0
            zeilen = (await s.scalars(select(AuftragTabelle).where(*bedingung).order_by(AuftragTabelle.eingang_s.desc()).offset(ab).limit(anzahl))).all()
            return [self._eintrag(z) for z in zeilen], gesamt

    async def kennzahlen(self, ab_s: float) -> Kennzahlen:
        """Abgeschlossene Aufträge seit `ab_s`: Anzahl je Ausgang, mittlere Wartezeit und Zeit bis zum ersten Stück."""
        async with self.db.sitzung() as s:
            zeilen = (await s.execute(select(AuftragTabelle.zustand, func.count(), func.avg(AuftragTabelle.start_s - AuftragTabelle.eingang_s),
                                             func.avg(AuftragTabelle.erstes_stueck_s))
                                      .where(AuftragTabelle.ende_s >= ab_s).group_by(AuftragTabelle.zustand))).all()
        k = Kennzahlen(ab_s=ab_s)
        for zustand, anzahl, warten, erstes in zeilen:
            if zustand == Auftragszustand.FERTIG.value:
                k.fertig, k.wartezeit_mittel_s, k.erstes_stueck_mittel_s = anzahl, warten, erstes
            elif zustand == Auftragszustand.FEHLGESCHLAGEN.value:
                k.fehler = anzahl
            elif zustand == Auftragszustand.ABGEBROCHEN.value:
                k.abgebrochen = anzahl
            elif zustand == Auftragszustand.ABGELEHNT.value:
                k.abgelehnt = anzahl
        return k

    async def offene_als_abgebrochen(self, ende_s: float) -> int:
        """Nach einem Neustart: was offen war, hat keine Verbindung mehr. Gibt die Zahl zurück."""
        offen = [z.value for z in OFFENE_ZUSTAENDE]
        async with self.db.sitzung() as s, s.begin():
            zeilen = (await s.scalars(select(AuftragTabelle).where(AuftragTabelle.zustand.in_(offen)))).all()
            for z in zeilen:
                z.zustand = Auftragszustand.ABGEBROCHEN.value
                z.grund = "neustart"
                z.begruendung = "Die Leitstelle wurde neu gestartet; die Verbindung der Anwendung bestand nicht mehr."
                z.ende_s = ende_s
            return len(zeilen)


class MassnahmenAblage:
    def __init__(self, db: Datenbank) -> None:
        self.db = db

    async def speichern(self, m: Massnahme) -> None:
        daten = m.model_dump(mode="json", exclude={"bewegungen"})
        async with self.db.sitzung() as s, s.begin():
            await s.merge(MassnahmeTabelle(**daten))

    async def neueste(self, anzahl: int = 50, ab: int = 0) -> tuple[list[Massnahme], int]:
        async with self.db.sitzung() as s:
            gesamt = await s.scalar(select(func.count()).select_from(MassnahmeTabelle)) or 0
            zeilen = (await s.scalars(select(MassnahmeTabelle).order_by(MassnahmeTabelle.zeit_s.desc()).offset(ab).limit(anzahl))).all()
            return [Massnahme(kennung=z.kennung, art=Massnahmenart(z.art), zustand=Massnahmenzustand(z.zustand), regel=z.regel, zeit_s=z.zeit_s, grund=z.grund,
                              gewinn_s=z.gewinn_s, aufwand_s=z.aufwand_s, schritte=list(z.schritte), auftraege=list(z.auftraege), knoten=z.knoten,
                              modell=z.modell, richtung=z.richtung) for z in zeilen], gesamt


class MessAblage:
    """Messwerk dauerhaft: je Art und Schlüssel der gleitende Mittelwert mit Anzahl."""

    ARTEN = ("ladezeiten", "startzeiten", "laufzeiten")

    def __init__(self, db: Datenbank) -> None:
        self.db = db

    async def laden(self) -> Messwerk:
        mw = Messwerk()
        async with self.db.sitzung() as s:
            for z in (await s.scalars(select(MessungTabelle))).all():
                if z.art in self.ARTEN:
                    getattr(mw, z.art)[z.schluessel] = Mittel(wert=z.wert, anzahl=z.anzahl)
        return mw

    async def speichern(self, mw: Messwerk) -> None:
        async with self.db.sitzung() as s, s.begin():
            for art in self.ARTEN:
                for schluessel, mittel in getattr(mw, art).items():
                    await s.merge(MessungTabelle(art=art, schluessel=schluessel, wert=mittel.wert, anzahl=mittel.anzahl))


class EinstellungAblage:
    def __init__(self, db: Datenbank) -> None:
        self.db = db

    async def _lesen(self, schluessel: str) -> dict | None:
        async with self.db.sitzung() as s:
            z = await s.get(EinstellungTabelle, schluessel)
            return dict(z.wert) if z else None

    async def _schreiben(self, schluessel: str, wert: dict) -> None:
        async with self.db.sitzung() as s, s.begin():
            await s.merge(EinstellungTabelle(schluessel=schluessel, wert=wert))

    async def regelwerk(self) -> Regelwerk:
        daten = await self._lesen("regelwerk")
        return Regelwerk.model_validate(daten) if daten else Regelwerk()

    async def regelwerk_speichern(self, r: Regelwerk) -> None:
        await self._schreiben("regelwerk", r.model_dump(mode="json"))

    async def betrieb(self) -> BetriebEinstellung:
        daten = await self._lesen("betrieb")
        return BetriebEinstellung.model_validate(daten) if daten else BetriebEinstellung()

    async def betrieb_speichern(self, b: BetriebEinstellung) -> None:
        await self._schreiben("betrieb", b.model_dump(mode="json"))


class PruefAblage:
    def __init__(self, db: Datenbank) -> None:
        self.db = db

    async def anhaengen(self, e: PruefEintrag) -> None:
        async with self.db.sitzung() as s, s.begin():
            s.add(PruefTabelle(zeit_s=e.zeit_s, wer=e.wer, was=e.was, gegenstand=e.gegenstand))

    async def neueste(self, anzahl: int = 100) -> list[PruefEintrag]:
        async with self.db.sitzung() as s:
            zeilen = (await s.scalars(select(PruefTabelle).order_by(PruefTabelle.nummer.desc()).limit(anzahl))).all()
            return [PruefEintrag(zeit_s=z.zeit_s, wer=z.wer, was=z.was, gegenstand=z.gegenstand) for z in zeilen]


class Ablage:
    """Alle Repositorien über einer Datenbank."""

    def __init__(self, db: Datenbank) -> None:
        self.db = db
        self.knoten = KnotenAblage(db)
        self.dienste = DienstAblage(db)
        self.anwendungen = AnwendungAblage(db)
        self.aliasse = AliasAblage(db)
        self.auftraege = AuftragAblage(db)
        self.massnahmen = MassnahmenAblage(db)
        self.messungen = MessAblage(db)
        self.einstellungen = EinstellungAblage(db)
        self.pruefung = PruefAblage(db)
