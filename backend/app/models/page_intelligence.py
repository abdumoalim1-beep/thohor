import uuid

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel


class PageGapAnalysis(TimestampedModel, table=True):
    """One row per (intent, competitor) gap analysis: what the competitor's
    winning page covers that our store's catalog summary does not (PRD
    section 26). Compares our whole-store context against their one page —
    not a structural page-to-page diff — since we don't yet have precise
    intent-to-our-page matching."""

    __tablename__ = "page_gap_analyses"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    intent_id: uuid.UUID = Field(foreign_key="intents.id", index=True)
    competitor_id: uuid.UUID = Field(foreign_key="competitors.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)
    agent_run_id: uuid.UUID | None = Field(default=None, foreign_key="agent_runs.id")

    competitor_url: str
    gaps: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    recommendation_summary: str
    confidence: float | None = None
    raw_artifact_uri: str | None = None
