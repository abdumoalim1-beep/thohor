"""onboarding leads table

Revision ID: 989b5eb23ad0
Revises: 5c72a0e913bf
Create Date: 2026-08-16 18:05:03.452772

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '989b5eb23ad0'
down_revision: Union[str, None] = '5c72a0e913bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# NOTE: autogenerate also detected pre-existing drift on
# analysis_component_snapshots (timestamp tz-awareness, payload JSON vs
# JSONB) unrelated to this change — left untouched here since it isn't
# part of this migration's scope; flagged separately.


def upgrade() -> None:
    op.create_table('onboarding_leads',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Uuid(), nullable=False),
    sa.Column('research_run_id', sa.Uuid(), nullable=True),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('contact', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.ForeignKeyConstraint(['research_run_id'], ['research_runs.id'], ),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_onboarding_leads_store_id'), 'onboarding_leads', ['store_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_onboarding_leads_store_id'), table_name='onboarding_leads')
    op.drop_table('onboarding_leads')
