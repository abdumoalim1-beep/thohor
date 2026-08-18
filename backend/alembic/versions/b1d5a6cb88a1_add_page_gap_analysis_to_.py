"""add page_gap_analysis to evidencesourcetype enum

Revision ID: b1d5a6cb88a1
Revises: d37cadd4ccf1
Create Date: 2026-08-11 13:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b1d5a6cb88a1'
down_revision: Union[str, None] = 'd37cadd4ccf1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Same lesson as 37819ad779df (Group B) and c701a3b01898 (Group C):
    # native Postgres ENUM value sets aren't auto-detected by alembic
    # autogenerate. Must run outside the alembic-managed transaction — PG
    # forbids using a value added by ALTER TYPE ... ADD VALUE within the
    # same transaction that added it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE evidencesourcetype ADD VALUE IF NOT EXISTS 'page_gap_analysis'")


def downgrade() -> None:
    # Removing a value from a Postgres enum type isn't directly supported
    # (would require rebuilding the type); intentional no-op.
    pass
