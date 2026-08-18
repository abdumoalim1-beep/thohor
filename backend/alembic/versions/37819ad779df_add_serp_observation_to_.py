"""add serp_observation to evidencesourcetype enum

Revision ID: 37819ad779df
Revises: f81a4081de50
Create Date: 2026-08-11 11:54:04.057305

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '37819ad779df'
down_revision: Union[str, None] = 'f81a4081de50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Native Postgres ENUM value sets are not auto-detected by alembic
    # autogenerate — adding a Python enum member requires this explicit
    # ALTER TYPE. Must run outside the alembic-managed transaction: PG
    # forbids using a value added by ALTER TYPE ... ADD VALUE within the
    # same transaction that added it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE evidencesourcetype ADD VALUE IF NOT EXISTS 'serp_observation'")


def downgrade() -> None:
    # Removing a value from a Postgres enum type isn't directly supported
    # (would require rebuilding the type); intentional no-op.
    pass
