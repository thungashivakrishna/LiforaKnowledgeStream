"""Add llm_call table for gateway cost tracking

Revision ID: a1b2c3d4e5f6
Revises: fe0609c80dfa
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'fe0609c80dfa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_call',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('stage', sa.String(50), nullable=False),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('prompt_id', sa.String(255), nullable=False),
        sa.Column('model_used', sa.String(255), nullable=False),
        sa.Column('model_requested', sa.String(255), nullable=False),
        sa.Column('fallback_depth', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cache_hit', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('status', sa.String(50), nullable=False, server_default='success'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_llm_call_stage_created', 'llm_call', ['stage', 'created_at'])
    op.create_index('ix_llm_call_document_id', 'llm_call', ['document_id'])


def downgrade() -> None:
    op.drop_index('ix_llm_call_document_id', table_name='llm_call')
    op.drop_index('ix_llm_call_stage_created', table_name='llm_call')
    op.drop_table('llm_call')
