"""Grenzen je Dienst: Anfragen je Minute (externe Anbieter) und Abstand der Zustandsabfrage

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-18 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('dienste', schema=None) as batch_op:
        batch_op.add_column(sa.Column('anfragen_je_minute', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('abgleich_s', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('dienste', schema=None) as batch_op:
        batch_op.drop_column('abgleich_s')
        batch_op.drop_column('anfragen_je_minute')
