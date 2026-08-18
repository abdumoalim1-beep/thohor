"""add web_search_citation to evidencesourcetype enum

Revision ID: 7c2e4a9f1b3d
Revises: 45fdedc04810
Create Date: 2026-08-17 03:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '7c2e4a9f1b3d'
down_revision: Union[str, None] = '45fdedc04810'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Same pattern as 37819ad779df: the Python EvidenceSourceType enum
    # (app/models/evidence.py) gained `web_search_citation` in Phase 1
    # (store identity resolver) but the native Postgres enum type was
    # never altered to match — must run outside the alembic transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE evidencesourcetype ADD VALUE IF NOT EXISTS 'web_search_citation'")


def downgrade() -> None:
    # Removing a value from a Postgres enum type isn't directly supported
    # (would require rebuilding the type); intentional no-op.
    pass
