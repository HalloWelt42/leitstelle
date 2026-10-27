"""Ablage: Migration, Tresor, Repositorien rund um einen Neustart."""

from leitstelle.kern.messungen import Messwerk
from leitstelle.kern.modelle import Regelwerk
from leitstelle.kern.werte import Auftragszustand as Z, Betriebsmodus, Faehigkeit as F, Prioritaet as P, Zone
from leitstelle.ports.ablage.datenbank import Datenbank
from leitstelle.ports.ablage.eintraege import AnwendungEintrag, AuftragEintrag, BetriebEinstellung, KnotenEintrag, PruefEintrag
from leitstelle.ports.ablage.repositorien import Ablage
from leitstelle.ports.tresor import Tresor, fingerabdruck, neuer_anwendungsschluessel


async def _ablage(tmp_path) -> Ablage:
    db = Datenbank(tmp_path / "test.sqlite")
    await db.oeffnen()
    return Ablage(db)


async def test_migration_und_wal(tmp_path):
    ablage = await _ablage(tmp_path)
    async with ablage.db.engine.connect() as v:
        modus = (await v.exec_driver_sql("PRAGMA journal_mode")).scalar()
        tabellen = {z[0] for z in (await v.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")).all()}
    assert modus == "wal"
    assert {"knoten", "dienste", "anwendungen", "auftraege", "massnahmen", "messungen", "einstellungen", "pruefprotokoll", "modell_aliasse"} <= tabellen
    await ablage.db.oeffnen()          # zweites Öffnen ist harmlos
    await ablage.db.schliessen()


async def test_tresor_und_anwendung_ueberdauern_neustart(tmp_path):
    tresor = Tresor(tmp_path / "tresor.schluessel")
    schluessel = neuer_anwendungsschluessel()
    assert schluessel.startswith("ls_") and len(schluessel) == 43
    ablage = await _ablage(tmp_path)
    a = AnwendungEintrag(kennung="a" * 32, name="Codehilfe", schluessel_fingerabdruck=fingerabdruck(schluessel),
                         schluessel_geheim=tresor.verschluesseln(schluessel), prioritaet=P.HOCH, zonen={Zone.HEIM, Zone.EXTERN},
                         ketten={F.TEXT: ["qwen/qwen3-coder-next", "qwen/qwen3-next-80b"]}, angelegt_s=1.0)
    await ablage.anwendungen.speichern(a)
    await ablage.db.schliessen()
    ablage2 = await _ablage(tmp_path)
    [b] = await ablage2.anwendungen.alle()
    assert b == a
    assert Tresor(tmp_path / "tresor.schluessel").entschluesseln(b.schluessel_geheim) == schluessel
    assert (tmp_path / "tresor.schluessel").stat().st_mode & 0o777 == 0o600
    await ablage2.db.schliessen()


async def test_auftraege_seitenweise_und_neustart(tmp_path):
    ablage = await _ablage(tmp_path)
    for i in range(7):
        await ablage.auftraege.speichern(AuftragEintrag(kennung=f"{i:032x}", anwendung="x", faehigkeit=F.TEXT, prioritaet=P.NORMAL,
                                                       zustand=Z.LAEUFT if i == 6 else Z.FERTIG, eingang_s=float(i)))
    seite, gesamt = await ablage.auftraege.seite(ab=0, anzahl=3)
    assert gesamt == 7 and [a.eingang_s for a in seite] == [6.0, 5.0, 4.0]
    assert await ablage.auftraege.offene_als_abgebrochen(99.0) == 1
    a = await ablage.auftraege.holen(f"{6:032x}")
    assert a.zustand == Z.ABGEBROCHEN and a.grund == "neustart"
    await ablage.db.schliessen()


async def test_messwerk_regelwerk_betrieb_pruefung(tmp_path):
    ablage = await _ablage(tmp_path)
    mw = Messwerk()
    mw.merke_ladezeit("glm", "mac", 12.0)
    mw.merke_laufzeit("zusage", "text", 30.0)
    await ablage.messungen.speichern(mw)
    mw2 = await ablage.messungen.laden()
    assert mw2.ladezeit("glm", "mac", 11.8).sekunden == 12.0 and mw2.ladezeit("glm", "mac", 11.8).gemessen
    r = Regelwerk(bedarfsfrist_s=90)
    await ablage.einstellungen.regelwerk_speichern(r)
    assert (await ablage.einstellungen.regelwerk()).bedarfsfrist_s == 90
    await ablage.einstellungen.betrieb_speichern(BetriebEinstellung(modus=Betriebsmodus.AUSLAUFEN, hintergrund_an=False))
    assert (await ablage.einstellungen.betrieb()).modus == Betriebsmodus.AUSLAUFEN
    await ablage.knoten.speichern(KnotenEintrag(kennung="k" * 32, name="Mac Studio", adresse="mac-studio.local", speicher_gb=128))
    assert (await ablage.knoten.alle())[0].name == "Mac Studio"
    await ablage.pruefung.anhaengen(PruefEintrag(zeit_s=1.0, wer="oberflaeche 192.168.1.20", was="Schlüssel aufgedeckt", gegenstand="codehilfe"))
    assert (await ablage.pruefung.neueste())[0].was == "Schlüssel aufgedeckt"
    await ablage.db.schliessen()


async def test_migration_mit_altbestand(tmp_path):
    """Eine Datenbank aus Fassung 0001 mit Aufträgen wird auf den neuesten Stand gehoben, ohne Verlust."""
    import sqlite3
    from alembic import command
    from leitstelle.ports.ablage.datenbank import alembic_konfig
    pfad = tmp_path / "alt.sqlite"
    command.upgrade(alembic_konfig(pfad), "0001")
    with sqlite3.connect(pfad) as v:
        v.execute("INSERT INTO auftraege (kennung, anwendung, faehigkeit, prioritaet, titel, zustand, begruendung, extern, umgeleitet, eingang_s, teilergebnis_zeichen, weg)"
                  " VALUES ('a', 'x', 'text', 1, '', 'fertig', '', 0, 0, 5.0, 0, 'fassade')")
    db = Datenbank(pfad)
    await db.oeffnen()
    a = await Ablage(db).auftraege.holen("a")
    assert a is not None and a.schritte == [] and a.eingang_s == 5.0 and a.arbeit is None
    assert await Ablage(db).bewegungen.neueste() == ([], 0)
    await db.schliessen()


async def test_x07_migration_0010_token_grenzen_und_proben(tmp_path):
    """Ein Hetzner-Eintrag aus 0.23 (nur Anfragegrenze) und ein Steckbrief von Hand bleiben; Token-Grenzen und aktive
    Parameter sind leer, Fähigkeitsproben lassen sich speichern."""
    import sqlite3
    from alembic import command
    from leitstelle.kern.werte import Faehigkeit
    from leitstelle.ports.ablage.datenbank import alembic_konfig
    from leitstelle.ports.ablage.eintraege import FaehigkeitsprobeEintrag
    pfad = tmp_path / "alt.sqlite"
    command.upgrade(alembic_konfig(pfad), "0009")
    with sqlite3.connect(pfad) as v:
        v.execute("INSERT INTO dienste (kennung, name, art, adresse, knoten, extern, zugang_geheim, plaetze, anfragen_je_minute, abgleich_s,"
                  " einbettung_instanzen, einbettung_spielraum_gb) VALUES ('h', 'Hetzner Experimental', 'extern_openai', 'https://inference.hetzner.com/api/v1',"
                  " NULL, 1, NULL, 4, 10, 900, 1, 4.0)")
        v.execute("INSERT INTO steckbriefe (familie, zweck, eignung, sprachen) VALUES ('Qwen/Qwen3.8-27B', 'Gründlich', '[]', '[]')")
    db = Datenbank(pfad)
    await db.oeffnen()
    ablage = Ablage(db)
    d = (await ablage.dienste.alle())[0]
    assert d.anfragen_je_minute == 10 and d.token_ein_je_minute is None and d.token_aus_je_minute is None
    assert (await ablage.steckbriefe.alle())[0].parameter_aktiv_mrd is None
    await ablage.proben.speichern(FaehigkeitsprobeEintrag(familie="Qwen/Qwen3.8-27B", faehigkeit=Faehigkeit.BILD_BESCHREIBEN, belegt=False, zeit_s=5.0))
    assert [(p.familie, p.belegt) for p in await ablage.proben.alle()] == [("Qwen/Qwen3.8-27B", False)]
    await db.schliessen()
