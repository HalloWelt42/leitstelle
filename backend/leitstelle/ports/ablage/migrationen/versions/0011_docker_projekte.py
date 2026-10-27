"""Anwendungen: ihre Container im Docker-Rechner (Compose-Projekte oder Containernamen)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-27 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('anwendungen', schema=None) as batch_op:
        batch_op.add_column(sa.Column('docker_projekte', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('anwendungen', schema=None) as batch_op:
        batch_op.drop_column('docker_projekte')
