"""Externe Anbieter klar abbilden: Token-Grenzen je Dienst, aktive Parameter im Steckbrief von Hand, Fähigkeitsproben

Token hinein und heraus je Minute (gleitend, je Schlüssel) sind wie die Anfragegrenze eine Einstellung des Dienstes;
NULL heißt keine Grenze. Im Steckbrief von Hand dürfen die aktiven Parameter stehen (Mischmodelle, deren Name es nicht
sagt). Fähigkeitsproben: je Modellfamilie und Fähigkeit das Ergebnis der letzten Probe von Hand (belegt oder nicht).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-27 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('dienste', schema=None) as batch_op:
        batch_op.add_column(sa.Column('token_ein_je_minute', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('token_aus_je_minute', sa.Integer(), nullable=True))
    with op.batch_alter_table('steckbriefe', schema=None) as batch_op:
        batch_op.add_column(sa.Column('parameter_aktiv_mrd', sa.Float(), nullable=True))
    op.create_table('faehigkeitsproben',
        sa.Column('familie', sa.String(length=255), nullable=False),
        sa.Column('faehigkeit', sa.String(length=30), nullable=False),
        sa.Column('belegt', sa.Boolean(), nullable=False),
        sa.Column('zeit_s', sa.Float(), nullable=False),
        sa.Column('meldung', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('familie', 'faehigkeit'))


def downgrade() -> None:
    op.drop_table('faehigkeitsproben')
    with op.batch_alter_table('steckbriefe', schema=None) as batch_op:
        batch_op.drop_column('parameter_aktiv_mrd')
    with op.batch_alter_table('dienste', schema=None) as batch_op:
        batch_op.drop_column('token_aus_je_minute')
        batch_op.drop_column('token_ein_je_minute')
