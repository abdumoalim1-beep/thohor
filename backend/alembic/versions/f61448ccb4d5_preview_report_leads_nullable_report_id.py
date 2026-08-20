"""preview report leads nullable report id

Revision ID: f61448ccb4d5
Revises: b2c431097e68
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f61448ccb4d5'
down_revision: Union[str, None] = 'b2c431097e68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('preview_report_leads', 'preview_report_id', existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM preview_report_leads WHERE preview_report_id IS NULL")
    op.alter_column('preview_report_leads', 'preview_report_id', existing_type=sa.Uuid(), nullable=False)
