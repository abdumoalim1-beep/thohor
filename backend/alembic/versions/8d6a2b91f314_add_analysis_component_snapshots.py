"""add independent analysis component snapshots

Revision ID: 8d6a2b91f314
Revises: 1ff548c3aaf4
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "8d6a2b91f314"
down_revision: Union[str, None] = "1ff548c3aaf4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_component_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("component", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("progress_completed", sa.Integer(), nullable=False),
        sa.Column("progress_total", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_run_id", "component", name="uq_analysis_snapshot_run_component"),
    )
    op.create_index(op.f("ix_analysis_component_snapshots_store_id"), "analysis_component_snapshots", ["store_id"])
    op.create_index(op.f("ix_analysis_component_snapshots_research_run_id"), "analysis_component_snapshots", ["research_run_id"])
    op.create_index(op.f("ix_analysis_component_snapshots_component"), "analysis_component_snapshots", ["component"])
    op.create_index(op.f("ix_analysis_component_snapshots_status"), "analysis_component_snapshots", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_analysis_component_snapshots_status"), table_name="analysis_component_snapshots")
    op.drop_index(op.f("ix_analysis_component_snapshots_component"), table_name="analysis_component_snapshots")
    op.drop_index(op.f("ix_analysis_component_snapshots_research_run_id"), table_name="analysis_component_snapshots")
    op.drop_index(op.f("ix_analysis_component_snapshots_store_id"), table_name="analysis_component_snapshots")
    op.drop_table("analysis_component_snapshots")
