"""Bildablage: erzeugte Bilder, die auf die Abholung durch ein Bildarchiv warten

Ist eine Anwendung ein Bildarchiv (neue Spalte anwendungen.bildarchiv), legt die Leitstelle jedes Bild, das eine andere Anwendung erzeugt, mit
Beschreibung, Startwert und Modell ab, bis das Archiv es abholt und quittiert (PROTOKOLL 6.3).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-03 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('anwendungen') as t:
        t.add_column(sa.Column('bildarchiv', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table('bildablage',
        sa.Column('kennung', sa.String(length=64), nullable=False),
        sa.Column('anwendung', sa.String(length=64), nullable=False),
        sa.Column('auftrag', sa.String(length=64), nullable=False),
        sa.Column('familie', sa.String(length=255), nullable=False),
        sa.Column('beschreibung', sa.Text(), nullable=False),
        sa.Column('seed', sa.Integer(), nullable=False),
        sa.Column('breite', sa.Integer(), nullable=False),
        sa.Column('hoehe', sa.Integer(), nullable=False),
        sa.Column('schritte', sa.Integer(), nullable=True),
        sa.Column('nummer', sa.Integer(), nullable=False),
        sa.Column('bytes', sa.Integer(), nullable=False),
        sa.Column('erzeugt_s', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('kennung'))
    op.create_index('ix_bildablage_erzeugt_s', 'bildablage', ['erzeugt_s'])


def downgrade() -> None:
    with op.batch_alter_table('anwendungen') as t:
        t.drop_column('bildarchiv')
    op.drop_index('ix_bildablage_erzeugt_s', table_name='bildablage')
    op.drop_table('bildablage')
