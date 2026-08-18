"""competitor identity discovery fields

Revision ID: 9d4f2a7c6e1b
Revises: 7c2e4a9f1b3d
Create Date: 2026-08-17 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '9d4f2a7c6e1b'
down_revision: Union[str, None] = '7c2e4a9f1b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# NOTE: stripped the usual unrelated analysis_component_snapshots autogenerate
# drift (see 2b7104c6db30's note) — only Phase 4's own changes are here.


def upgrade() -> None:
    op.add_column(
        'competitors',
        sa.Column('confirmation_status', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='pending_user_confirmation'),
    )
    op.create_index(op.f('ix_competitors_confirmation_status'), 'competitors', ['confirmation_status'], unique=False)

    # Same lesson as 7c2e4a9f1b3d (learned the hard way, live, on this same
    # session): a new Python CompetitorType member needs the native Postgres
    # enum type altered explicitly — autogenerate never detects this, and
    # skipping it makes every INSERT using the new value fail at runtime.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE competitortype ADD VALUE IF NOT EXISTS 'identity_web_search'")


def downgrade() -> None:
    op.drop_index(op.f('ix_competitors_confirmation_status'), table_name='competitors')
    op.drop_column('competitors', 'confirmation_status')
    # Removing a value from a Postgres enum type isn't directly supported
    # (would require rebuilding the type); intentional no-op.
