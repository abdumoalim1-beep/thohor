"""preview report leads survey fields

Revision ID: d4f8b3c21a67
Revises: c3e7a2f19b4d
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = 'd4f8b3c21a67'
down_revision: Union[str, None] = 'c3e7a2f19b4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pre-existing rows only ever came from this session's own manual
    # verification of the old contact/phone shape, never a real lead —
    # safe to clear rather than backfill.
    op.execute("DELETE FROM preview_report_leads")
    op.drop_column('preview_report_leads', 'contact')
    op.drop_column('preview_report_leads', 'phone')
    op.add_column('preview_report_leads', sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False))
    op.add_column('preview_report_leads', sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=False))
    op.add_column('preview_report_leads', sa.Column('report_feedback', sqlmodel.sql.sqltypes.AutoString(), nullable=False))
    op.add_column('preview_report_leads', sa.Column('interest_level', sqlmodel.sql.sqltypes.AutoString(), nullable=False))


def downgrade() -> None:
    op.execute("DELETE FROM preview_report_leads")
    op.drop_column('preview_report_leads', 'interest_level')
    op.drop_column('preview_report_leads', 'report_feedback')
    op.drop_column('preview_report_leads', 'email')
    op.drop_column('preview_report_leads', 'name')
    op.add_column('preview_report_leads', sa.Column('contact', sqlmodel.sql.sqltypes.AutoString(), nullable=False))
    op.add_column('preview_report_leads', sa.Column('phone', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
