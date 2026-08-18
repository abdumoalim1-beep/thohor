import uuid
from datetime import datetime

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel, utcnow


class PageObservation(TimestampedModel, table=True):
    """One row per crawled page per run — not one row per extracted field.

    raw_artifact_uri points at the untouched HTML in MinIO (raw evidence).
    normalized_extraction holds deterministic facts (title, H1, schema.org,
    prices, ...). extracted_entities holds AI-enrichment output (category
    labels, audience, attributes) and must be traceable back to the
    ai_executions row that produced it via source metadata.
    """

    __tablename__ = "page_observations"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)
    agent_run_id: uuid.UUID | None = Field(default=None, foreign_key="agent_runs.id")
    page_id: uuid.UUID | None = Field(default=None, foreign_key="pages.id", index=True)

    source_url: str
    source: str = Field(default="crawler")
    extractor_version: str

    raw_artifact_uri: str | None = None
    normalized_extraction: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))
    extracted_entities: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))

    observed_at: datetime = Field(default_factory=utcnow)
