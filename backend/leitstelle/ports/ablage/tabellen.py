"""Tabellen der Ablage (SQLAlchemy 2). Änderungen nur zusammen mit einer Migration unter migrationen/."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Basis(DeclarativeBase):
    pass


class KnotenTabelle(Basis):
    __tablename__ = "knoten"
    kennung: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    adresse: Mapped[str] = mapped_column(String(255))
    zone: Mapped[str] = mapped_column(String(20))
    speicher_gb: Mapped[float] = mapped_column(Float)
    system_gb: Mapped[float] = mapped_column(Float)
    budget_fest_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    hintergrund_von: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hintergrund_bis: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_fingerabdruck: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_geheim: Mapped[str | None] = mapped_column(Text, nullable=True)


class DienstTabelle(Basis):
    __tablename__ = "dienste"
    kennung: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    art: Mapped[str] = mapped_column(String(40))
    adresse: Mapped[str] = mapped_column(String(255))
    knoten: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extern: Mapped[bool] = mapped_column(Boolean, default=False)
    zugang_geheim: Mapped[str | None] = mapped_column(Text, nullable=True)
    plaetze: Mapped[int] = mapped_column(Integer, default=4)


class AnwendungTabelle(Basis):
    __tablename__ = "anwendungen"
    kennung: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    schluessel_fingerabdruck: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    schluessel_geheim: Mapped[str] = mapped_column(Text)
    prioritaet: Mapped[int] = mapped_column(Integer)
    faehigkeiten: Mapped[list[str]] = mapped_column(JSON)
    zonen: Mapped[list[str]] = mapped_column(JSON)
    extern_erlaubt: Mapped[bool] = mapped_column(Boolean, default=False)
    gleichzeitig: Mapped[int] = mapped_column(Integer, default=4)
    ketten: Mapped[dict[str, Any]] = mapped_column(JSON)
    gesperrt: Mapped[bool] = mapped_column(Boolean, default=False)
    sperrgrund: Mapped[str] = mapped_column(Text, default="")
    angelegt_s: Mapped[float] = mapped_column(Float)


class AliasTabelle(Basis):
    __tablename__ = "modell_aliasse"
    alias: Mapped[str] = mapped_column(String(255), primary_key=True)
    familie: Mapped[str] = mapped_column(String(255))


class AuftragTabelle(Basis):
    __tablename__ = "auftraege"
    kennung: Mapped[str] = mapped_column(String(32), primary_key=True)
    anwendung: Mapped[str] = mapped_column(String(32), index=True)
    faehigkeit: Mapped[str] = mapped_column(String(30))
    prioritaet: Mapped[int] = mapped_column(Integer)
    titel: Mapped[str] = mapped_column(Text, default="")
    zustand: Mapped[str] = mapped_column(String(30), index=True)
    grund: Mapped[str | None] = mapped_column(String(40), nullable=True)
    begruendung: Mapped[str] = mapped_column(Text, default="")
    festes_modell: Mapped[str | None] = mapped_column(String(255), nullable=True)
    familie: Mapped[str | None] = mapped_column(String(255), nullable=True)
    modell_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dienst: Mapped[str | None] = mapped_column(String(32), nullable=True)
    knoten: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extern: Mapped[bool] = mapped_column(Boolean, default=False)
    umgeleitet: Mapped[int] = mapped_column(Integer, default=0)
    eingang_s: Mapped[float] = mapped_column(Float, index=True)
    start_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    ende_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    erstes_stueck_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    token_ein: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_aus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    teilergebnis_zeichen: Mapped[int] = mapped_column(Integer, default=0)
    weg: Mapped[str] = mapped_column(String(20), default="fassade")
    schritte: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    arbeit: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)


class MassnahmeTabelle(Basis):
    __tablename__ = "massnahmen"
    kennung: Mapped[str] = mapped_column(String(32), primary_key=True)
    art: Mapped[str] = mapped_column(String(40))
    zustand: Mapped[str] = mapped_column(String(30))
    regel: Mapped[str] = mapped_column(String(80))
    zeit_s: Mapped[float] = mapped_column(Float, index=True)
    grund: Mapped[str] = mapped_column(Text)
    gewinn_s: Mapped[float] = mapped_column(Float)
    aufwand_s: Mapped[float] = mapped_column(Float)
    schritte: Mapped[list[str]] = mapped_column(JSON)
    auftraege: Mapped[list[str]] = mapped_column(JSON)
    knoten: Mapped[str | None] = mapped_column(String(32), nullable=True)
    modell: Mapped[str | None] = mapped_column(String(255), nullable=True)
    richtung: Mapped[str | None] = mapped_column(String(20), nullable=True)


class MessungTabelle(Basis):
    __tablename__ = "messungen"
    art: Mapped[str] = mapped_column(String(20), primary_key=True)        # ladezeit, startzeit, laufzeit
    schluessel: Mapped[str] = mapped_column(String(255), primary_key=True)
    wert: Mapped[float] = mapped_column(Float)
    anzahl: Mapped[int] = mapped_column(Integer)


class EinstellungTabelle(Basis):
    __tablename__ = "einstellungen"
    schluessel: Mapped[str] = mapped_column(String(40), primary_key=True)
    wert: Mapped[dict[str, Any]] = mapped_column(JSON)


class BewegungTabelle(Basis):
    """Laden und Entladen als Rohdaten: nur anhängen."""

    __tablename__ = "bewegungen"
    nummer: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zeit_s: Mapped[float] = mapped_column(Float, index=True)
    richtung: Mapped[str] = mapped_column(String(20))
    familie: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    knoten: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gb: Mapped[float] = mapped_column(Float)
    dauer_s: Mapped[float] = mapped_column(Float)
    ausgang: Mapped[str] = mapped_column(String(20))
    meldung: Mapped[str] = mapped_column(Text, default="")


class PruefTabelle(Basis):
    """Prüfprotokoll: nur anhängen, nie ändern oder löschen."""

    __tablename__ = "pruefprotokoll"
    nummer: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zeit_s: Mapped[float] = mapped_column(Float, index=True)
    wer: Mapped[str] = mapped_column(String(120))
    was: Mapped[str] = mapped_column(Text)
    gegenstand: Mapped[str] = mapped_column(String(255), default="")
