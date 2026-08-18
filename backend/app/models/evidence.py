import uuid
from datetime import datetime
from enum import Enum

from sqlmodel import Field

from app.models.base import TimestampedModel, utcnow


class EvidenceSourceType(str, Enum):
    page_observation = "page_observation"
    ai_execution = "ai_execution"
    serp_observation = "serp_observation"
    ai_visibility_observation = "ai_visibility_observation"
    page_gap_analysis = "page_gap_analysis"
    implementation_change_detection = "implementation_change_detection"
    # A single web_search result URL cited by an identity/competitor
    # resolution call. Not a real FK — source_id is deterministically
    # derived from the URL (uuid.uuid5(NAMESPACE_URL, source_url)) since
    # there is no other-table row to point at; `summary` carries the
    # url+title so the citation is still human-readable without a join.
    web_search_citation = "web_search_citation"


class Evidence(TimestampedModel, table=True):
    """The trust layer: a pointer + confidence on top of a page_observation
    or ai_execution. Deliberately NOT one row per field (no evidence for
    every H1/meta/link) — evidence is created for claims that matter,
    referencing the observation/execution that backs them.

    Recommendations (built in a later milestone group) will reference
    evidence_id here, never raw observations directly.
    """

    __tablename__ = "evidence"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)

    source_type: EvidenceSourceType
    # Polymorphic reference to page_observations.id or ai_executions.id.
    # No FK constraint since it targets one of two tables based on source_type.
    source_id: uuid.UUID

    confidence: float | None = None
    summary: str | None = None
    observed_at: datetime = Field(default_factory=utcnow)
