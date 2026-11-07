"""Rolle der Rechner: Fähigkeiten, deren Arbeit zuerst auf diesen Rechner geht (Arbeitslogik 07.11.2026, LS-16)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-07 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('knoten') as t:
        t.add_column(sa.Column('bevorzugt_fuer', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('knoten') as t:
        t.drop_column('bevorzugt_fuer')
