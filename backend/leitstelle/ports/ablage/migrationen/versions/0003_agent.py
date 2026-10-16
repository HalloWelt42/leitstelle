"""Knoten-Agent: Schlüssel je Knoten (Fingerabdruck zum Erkennen, verschlüsselt zum Aufdecken)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16 22:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('knoten', schema=None) as batch_op:
        batch_op.add_column(sa.Column('agent_fingerabdruck', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('agent_geheim', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('knoten', schema=None) as batch_op:
        batch_op.drop_column('agent_geheim')
        batch_op.drop_column('agent_fingerabdruck')
