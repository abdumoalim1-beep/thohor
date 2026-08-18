"""add ai_visibility_observation to evidencesourcetype enum

Revision ID: c701a3b01898
Revises: 84605443d96c
Create Date: 2026-08-11 12:23:37.937767

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c701a3b01898'
down_revision: Union[str, None] = '84605443d96c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Same lesson as 37819ad779df (Group B): native Postgres ENUM value
    # sets aren't auto-detected by alembic autogenerate. Must run outside
    # the alembic-managed transaction — PG forbids using a value added by
    # ALTER TYPE ... ADD VALUE within the same transaction that added it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE evidencesourcetype ADD VALUE IF NOT EXISTS 'ai_visibility_observation'")


def downgrade() -> None:
    # Removing a value from a Postgres enum type isn't directly supported
    # (would require rebuilding the type); intentional no-op.
    pass
