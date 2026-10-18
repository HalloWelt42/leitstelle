"""Steckbriefe: von Hand eingetragen, wofür ein Modell gemacht ist (Selbstauskunft, PROTOKOLL 4.8)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-18 22:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('steckbriefe',
        sa.Column('familie', sa.String(length=255), nullable=False),
        sa.Column('zweck', sa.Text(), nullable=False),
        sa.Column('eignung', sa.JSON(), nullable=False),
        sa.Column('sprachen', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('familie'))


def downgrade() -> None:
    op.drop_table('steckbriefe')
