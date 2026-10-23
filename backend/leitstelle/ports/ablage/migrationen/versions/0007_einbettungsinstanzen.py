"""Einbettungsinstanzen je Dienst: Höchstzahl und Spielraum im Budget des Rechners

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23 23:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('dienste', schema=None) as batch_op:
        batch_op.add_column(sa.Column('einbettung_instanzen', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('einbettung_spielraum_gb', sa.Float(), nullable=False, server_default='4.0'))


def downgrade() -> None:
    with op.batch_alter_table('dienste', schema=None) as batch_op:
        batch_op.drop_column('einbettung_spielraum_gb')
        batch_op.drop_column('einbettung_instanzen')
