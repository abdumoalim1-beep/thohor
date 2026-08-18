"""visibility_questions_table

Revision ID: 8d3342fedef7
Revises: 9d4f2a7c6e1b
Create Date: 2026-08-17 10:11:50.512925

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '8d3342fedef7'
down_revision: Union[str, None] = '9d4f2a7c6e1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# NOTE: stripped the usual unrelated analysis_component_snapshots
# autogenerate drift (see 2b7104c6db30's note) — only Phase 5's new table
# is included here.


def upgrade() -> None:
    op.create_table('visibility_questions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Uuid(), nullable=False),
    sa.Column('text', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('category', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('normalized_text', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('source_research_run_id', sa.Uuid(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['source_research_run_id'], ['research_runs.id'], ),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_visibility_questions_category'), 'visibility_questions', ['category'], unique=False)
    op.create_index(op.f('ix_visibility_questions_normalized_text'), 'visibility_questions', ['normalized_text'], unique=False)
    op.create_index(op.f('ix_visibility_questions_store_id'), 'visibility_questions', ['store_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_visibility_questions_store_id'), table_name='visibility_questions')
    op.drop_index(op.f('ix_visibility_questions_normalized_text'), table_name='visibility_questions')
    op.drop_index(op.f('ix_visibility_questions_category'), table_name='visibility_questions')
    op.drop_table('visibility_questions')
