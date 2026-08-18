import uuid
from datetime import datetime

from sqlalchemy import Column, UniqueConstraint
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel


class AnalysisComponentSnapshot(TimestampedModel, table=True):
    """Independently publishable state for one customer-facing analysis surface.

    A new research run may update one component without hiding the latest
    completed snapshot of any other component.
    """

    __tablename__ = "analysis_component_snapshots"
    __table_args__ = (UniqueConstraint("research_run_id", "component", name="uq_analysis_snapshot_run_component"),)

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)
    component: str = Field(index=True)  # basic | google | ai | competitors | opportunities
    status: str = Field(default="not_started", index=True)
    progress_completed: int = 0
    progress_total: int = 0
    payload: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
