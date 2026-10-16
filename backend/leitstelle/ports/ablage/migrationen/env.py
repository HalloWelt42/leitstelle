"""Alembic-Umgebung: Migrationen laufen synchron gegen dieselbe SQLite-Datei wie der Dienst."""

from alembic import context
from sqlalchemy import engine_from_config, pool

from leitstelle.ports.ablage.tabellen import Basis

konfig = context.config
ziel = Basis.metadata


def offline() -> None:
    context.configure(url=konfig.get_main_option("sqlalchemy.url"), target_metadata=ziel, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def online() -> None:
    engine = engine_from_config(konfig.get_section(konfig.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as verbindung:
        context.configure(connection=verbindung, target_metadata=ziel, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    offline()
else:
    online()
