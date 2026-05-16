"""Add missing enum values

Revision ID: 2184150461a6
Revises: 001
Create Date: 2026-05-13 22:08:54.351331

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2184150461a6'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Handle PostgreSQL enums - ALTER TYPE ADD VALUE cannot be run in a transaction block
    # in some Postgres versions/configurations, but Alembic op.execute usually works.
    # To be safe on all versions, we use op.get_bind().execute with COMMIT if needed,
    # but standard Alembic practice is op.execute.
    
    op.execute("ALTER TYPE framework ADD VALUE IF NOT EXISTS 'PREVENTIVE_MEDICINE'")
    op.execute("ALTER TYPE framework ADD VALUE IF NOT EXISTS 'DIAGNOSTICS_AND_LABS'")
    op.execute("ALTER TYPE framework ADD VALUE IF NOT EXISTS 'PHARMACOLOGY_MEDICINE'")
    
    op.execute("ALTER TYPE tagtype ADD VALUE IF NOT EXISTS 'NUTRIENT'")
    op.execute("ALTER TYPE tagtype ADD VALUE IF NOT EXISTS 'ACTIVITY'")
    op.execute("ALTER TYPE tagtype ADD VALUE IF NOT EXISTS 'POPULATION'")
    op.execute("ALTER TYPE tagtype ADD VALUE IF NOT EXISTS 'EVIDENCE_LEVEL'")
    op.execute("ALTER TYPE tagtype ADD VALUE IF NOT EXISTS 'CONTRAINDICATION'")


def downgrade() -> None:
    # Removing enum values is not supported in PostgreSQL (ALTER TYPE DROP VALUE doesn't exist)
    # Usually you'd have to drop and recreate the type, which is complex.
    pass
