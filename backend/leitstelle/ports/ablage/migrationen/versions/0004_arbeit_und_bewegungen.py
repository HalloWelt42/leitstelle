"""Arbeit je Auftrag (Kopf X-Leitstelle-Arbeit) und Bewegungen: Laden und Entladen als Rohdaten

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-18 19:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('auftraege', schema=None) as batch_op:
        batch_op.add_column(sa.Column('arbeit', sa.String(length=100), nullable=True))
        batch_op.create_index(batch_op.f('ix_auftraege_arbeit'), ['arbeit'], unique=False)
    op.create_table('bewegungen',
        sa.Column('nummer', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('zeit_s', sa.Float(), nullable=False),
        sa.Column('richtung', sa.String(length=20), nullable=False),
        sa.Column('familie', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('knoten', sa.String(length=32), nullable=True),
        sa.Column('gb', sa.Float(), nullable=False),
        sa.Column('dauer_s', sa.Float(), nullable=False),
        sa.Column('ausgang', sa.String(length=20), nullable=False),
        sa.Column('meldung', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('nummer'))
    with op.batch_alter_table('bewegungen', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bewegungen_zeit_s'), ['zeit_s'], unique=False)
        batch_op.create_index(batch_op.f('ix_bewegungen_familie'), ['familie'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('bewegungen', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bewegungen_familie'))
        batch_op.drop_index(batch_op.f('ix_bewegungen_zeit_s'))
    op.drop_table('bewegungen')
    with op.batch_alter_table('auftraege', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_auftraege_arbeit'))
        batch_op.drop_column('arbeit')
