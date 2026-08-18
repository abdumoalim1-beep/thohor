import uuid
from datetime import datetime

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel, utcnow


class MeasurementBaseline(TimestampedModel, table=True):
    """The 'before' state, captured exactly once — the moment a
    Recommendation is created (Group F design decision #1: 'لا نحاول إنشاء
    baseline بعد التنفيذ'). Never updated afterward."""

    __tablename__ = "measurement_baselines"

    recommendation_id: uuid.UUID = Field(foreign_key="recommendations.id", index=True, unique=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id")
    captured_at: datetime = Field(default_factory=utcnow)

    target_queries: list[dict] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    target_prompts: list[dict] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    google_visibility: float | None = None
    ai_visibility: float | None = None
    page_metrics: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))
    competitor_visibility: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))


class MeasurementSnapshot(TimestampedModel, table=True):
    """One 'after' data point — re-measurement of exactly the Control Set
    captured in the baseline's target_queries/target_prompts (Group F
    design decision #3), never a fresh Discovery pass. Immutable: each
    monitoring pass inserts a new row."""

    __tablename__ = "measurement_snapshots"

    recommendation_id: uuid.UUID = Field(foreign_key="recommendations.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id")
    captured_at: datetime = Field(default_factory=utcnow)

    google_visibility: float | None = None
    ai_visibility: float | None = None
    page_metrics: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))
