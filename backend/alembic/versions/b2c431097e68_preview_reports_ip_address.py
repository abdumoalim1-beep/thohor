"""preview reports ip_address (abuse guard)

Revision ID: b2c431097e68
Revises: d4f8b3c21a67
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = 'b2c431097e68'
down_revision: Union[str, None] = 'd4f8b3c21a67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('preview_reports', sa.Column('ip_address', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_index(op.f('ix_preview_reports_ip_address'), 'preview_reports', ['ip_address'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_preview_reports_ip_address'), table_name='preview_reports')
    op.drop_column('preview_reports', 'ip_address')
