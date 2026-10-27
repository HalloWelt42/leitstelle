"""Modell-Läufer immer direkt: der Weg über die Durchleitung des Maschinenraums entfällt (Spalte ueber_maschinenraum)

Die Leitstelle ist zentrale Steuerung und Überwachung; den Modell-Läufer spricht sie direkt an, durch den Maschinenraum
gehen nur seine Dienste.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-27 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('dienste', schema=None) as batch_op:
        batch_op.drop_column('ueber_maschinenraum')


def downgrade() -> None:
    with op.batch_alter_table('dienste', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ueber_maschinenraum', sa.Boolean(), nullable=False, server_default=sa.false()))
