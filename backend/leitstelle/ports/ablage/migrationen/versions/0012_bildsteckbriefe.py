"""Bild-Steckbriefe: je Bilddienst, was sein Modell annimmt (Größen, Schritte, Anzahl, Bearbeiten), wie der Dienst es sagt

Die Leitstelle liest den Steckbrief eines Bilddienstes im üblichen Bildformat nach jedem Start (GET /v1/models) und hält
ihn über Neustarts, damit sie Anfragen prüfen kann, bevor sie den Dienst startet.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-27 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('bildsteckbriefe',
        sa.Column('familie', sa.String(length=255), nullable=False),
        sa.Column('steckbrief', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('familie'))


def downgrade() -> None:
    op.drop_table('bildsteckbriefe')
