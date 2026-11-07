"""Ketten der Anwendungen entfallen: das Modell wählt immer die Anwendung (Arbeitslogik 07.11.2026, LS-19)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-07 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('anwendungen') as t:
        t.drop_column('ketten')


def downgrade() -> None:
    with op.batch_alter_table('anwendungen') as t:
        t.add_column(sa.Column('ketten', sa.JSON(), nullable=False, server_default='{}'))
