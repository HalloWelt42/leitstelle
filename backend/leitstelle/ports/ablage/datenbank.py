"""Verbindung zur SQLite-Datenbank (WAL) und Migrationen beim Start."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

MIGRATIONEN = Path(__file__).resolve().parent / "migrationen"


def _pragmas(dbapi_verbindung, _eintrag) -> None:
    zeiger = dbapi_verbindung.cursor()
    zeiger.execute("PRAGMA journal_mode=WAL")
    zeiger.execute("PRAGMA synchronous=NORMAL")
    zeiger.execute("PRAGMA busy_timeout=5000")
    zeiger.close()


def alembic_konfig(pfad: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONEN))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{pfad}")
    return cfg


def migrieren(pfad: Path) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_konfig(pfad), "head")


class Datenbank:
    def __init__(self, pfad: Path) -> None:
        self.pfad = pfad
        self.engine: AsyncEngine = create_async_engine(f"sqlite+aiosqlite:///{pfad}")
        event.listen(self.engine.sync_engine, "connect", _pragmas)
        self.sitzung = async_sessionmaker(self.engine, expire_on_commit=False)

    async def oeffnen(self) -> None:
        await asyncio.to_thread(migrieren, self.pfad)

    async def schliessen(self) -> None:
        await self.engine.dispose()
