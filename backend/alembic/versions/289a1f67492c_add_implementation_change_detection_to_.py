"""add implementation_change_detection to evidencesourcetype enum

Revision ID: 289a1f67492c
Revises: 00d592a7cbc5
Create Date: 2026-08-11 17:24:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '289a1f67492c'
down_revision: Union[str, None] = '00d592a7cbc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Same recurring lesson (Groups B/C/D/D2): native Postgres ENUM value
    # sets aren't auto-detected by alembic autogenerate. Must run outside
    # the alembic-managed transaction — PG forbids using a value added by
    # ALTER TYPE ... ADD VALUE within the same transaction that added it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE evidencesourcetype ADD VALUE IF NOT EXISTS 'implementation_change_detection'")


def downgrade() -> None:
    # Removing a value from a Postgres enum type isn't directly supported
    # (would require rebuilding the type); intentional no-op.
    pass
