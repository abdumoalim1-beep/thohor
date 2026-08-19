"""preview reports table

Revision ID: c3e7a2f19b4d
Revises: a1f3c9d8e7b2
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = 'c3e7a2f19b4d'
down_revision: Union[str, None] = 'a1f3c9d8e7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('preview_reports',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_url', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('stage', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('report', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_preview_reports_status'), 'preview_reports', ['status'], unique=False)

    op.create_table('preview_report_leads',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('preview_report_id', sa.Uuid(), nullable=False),
    sa.Column('contact', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('phone', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.ForeignKeyConstraint(['preview_report_id'], ['preview_reports.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_preview_report_leads_preview_report_id'), 'preview_report_leads', ['preview_report_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_preview_report_leads_preview_report_id'), table_name='preview_report_leads')
    op.drop_table('preview_report_leads')
    op.drop_index(op.f('ix_preview_reports_status'), table_name='preview_reports')
    op.drop_table('preview_reports')
