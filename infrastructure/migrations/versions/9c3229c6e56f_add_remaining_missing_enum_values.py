"""Add remaining missing enum values

Revision ID: 9c3229c6e56f
Revises: 2184150461a6
Create Date: 2026-05-13 22:12:57.834746

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c3229c6e56f'
down_revision: Union[str, None] = '2184150461a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'REJECTED'")
    op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'CLINICAL_REPORT_SOURCE'")
    op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'PRESCRIPTION_SOURCE'")


def downgrade() -> None:
    pass
