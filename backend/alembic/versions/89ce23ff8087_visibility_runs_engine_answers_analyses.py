"""visibility_runs_engine_answers_analyses

Revision ID: 89ce23ff8087
Revises: 8d3342fedef7
Create Date: 2026-08-17 11:22:38.833235

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '89ce23ff8087'
down_revision: Union[str, None] = '8d3342fedef7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# NOTE: stripped the usual unrelated analysis_component_snapshots
# autogenerate drift (see 2b7104c6db30's note) — only the 3 new tables for
# the re-scoped Part 2 MVP (question running + answer analysis) are here.


def upgrade() -> None:
    op.create_table('visibility_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Uuid(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('engines_attempted', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
    sa.Column('questions_count', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_visibility_runs_status'), 'visibility_runs', ['status'], unique=False)
    op.create_index(op.f('ix_visibility_runs_store_id'), 'visibility_runs', ['store_id'], unique=False)
    op.create_table('engine_answers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('visibility_run_id', sa.Uuid(), nullable=False),
    sa.Column('question_id', sa.Uuid(), nullable=False),
    sa.Column('store_id', sa.Uuid(), nullable=False),
    sa.Column('engine', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('engine_model', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('raw_answer', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('sources', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
    sa.Column('language', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('country', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('executed_at', sa.DateTime(), nullable=False),
    sa.Column('ai_execution_id', sa.Uuid(), nullable=True),
    sa.ForeignKeyConstraint(['question_id'], ['visibility_questions.id'], ),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ),
    sa.ForeignKeyConstraint(['visibility_run_id'], ['visibility_runs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_engine_answers_engine'), 'engine_answers', ['engine'], unique=False)
    op.create_index(op.f('ix_engine_answers_question_id'), 'engine_answers', ['question_id'], unique=False)
    op.create_index(op.f('ix_engine_answers_store_id'), 'engine_answers', ['store_id'], unique=False)
    op.create_index(op.f('ix_engine_answers_visibility_run_id'), 'engine_answers', ['visibility_run_id'], unique=False)
    op.create_table('engine_answer_analyses',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('engine_answer_id', sa.Uuid(), nullable=False),
    sa.Column('store_id', sa.Uuid(), nullable=False),
    sa.Column('brand_mentioned', sa.Boolean(), nullable=False),
    sa.Column('mention_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('mention_rank', sa.Integer(), nullable=True),
    sa.Column('recommendation_rank', sa.Integer(), nullable=True),
    sa.Column('competitors_mentioned', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
    sa.Column('evidence_quote', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['engine_answer_id'], ['engine_answers.id'], ),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_engine_answer_analyses_engine_answer_id'), 'engine_answer_analyses', ['engine_answer_id'], unique=True)
    op.create_index(op.f('ix_engine_answer_analyses_store_id'), 'engine_answer_analyses', ['store_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_engine_answer_analyses_store_id'), table_name='engine_answer_analyses')
    op.drop_index(op.f('ix_engine_answer_analyses_engine_answer_id'), table_name='engine_answer_analyses')
    op.drop_table('engine_answer_analyses')
    op.drop_index(op.f('ix_engine_answers_visibility_run_id'), table_name='engine_answers')
    op.drop_index(op.f('ix_engine_answers_store_id'), table_name='engine_answers')
    op.drop_index(op.f('ix_engine_answers_question_id'), table_name='engine_answers')
    op.drop_index(op.f('ix_engine_answers_engine'), table_name='engine_answers')
    op.drop_table('engine_answers')
    op.drop_index(op.f('ix_visibility_runs_store_id'), table_name='visibility_runs')
    op.drop_index(op.f('ix_visibility_runs_status'), table_name='visibility_runs')
    op.drop_table('visibility_runs')
