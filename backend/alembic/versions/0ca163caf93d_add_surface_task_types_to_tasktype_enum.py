"""add surface task types to tasktype enum

Revision ID: 0ca163caf93d
Revises: 1c522554b6c4
Create Date: 2026-08-11 22:07:45.955697

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '0ca163caf93d'
down_revision: Union[str, None] = '1c522554b6c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Same recurring lesson (Groups B/C/D/D2/F.5-0's evidencesourcetype
    # migrations): native Postgres ENUM value sets aren't auto-detected by
    # alembic autogenerate. Must run outside the alembic-managed
    # transaction — PG forbids using a value added by ALTER TYPE ... ADD
    # VALUE within the same transaction that added it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'search_google'")
        op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'ai_visibility_chatgpt'")
        op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'ai_visibility_gemini'")
        op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'ai_visibility_claude'")
        op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'validate_cross_surface_finding'")


def downgrade() -> None:
    # Removing a value from a Postgres enum type isn't directly supported
    # (would require rebuilding the type); intentional no-op.
    pass
