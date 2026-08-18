import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel, utcnow


class SerpExecutionStatus(str, Enum):
    success = "success"
    error = "error"


class SerpObservation(TimestampedModel, table=True):
    """One row per (intent, keyword) SERP query — not one row per ranked
    result. `results` holds the top organic results as-is (this is where
    competitor domains come from for free in a later milestone group);
    client_rank/client_url promote the store's own position for fast
    querying. Immutable: a re-measurement inserts a new row with a new
    observed_at, never updates this one."""

    __tablename__ = "serp_observations"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    intent_id: uuid.UUID = Field(foreign_key="intents.id", index=True)
    stable_intent_id: uuid.UUID | None = Field(default=None, foreign_key="stable_intents.id", index=True)
    keyword_id: uuid.UUID = Field(foreign_key="keywords.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)
    agent_run_id: uuid.UUID | None = Field(default=None, foreign_key="agent_runs.id")
    # NULL = produced by the fixed control-cadence serp_batch phase task
    # (unchanged meaning for every row from Groups A-D). Set only when a
    # Discovery-tier task (e.g. validate_finding) triggers an extra,
    # off-cadence SERP check — keeps Control measurement queries
    # (compute_visibility_metrics) separable from Discovery noise later
    # without having touched that function's behavior now.
    origin_task_id: uuid.UUID | None = Field(default=None, foreign_key="research_tasks.id", index=True)

    engine: str = Field(default="google")
    country: str
    language: str
    device: str = Field(default="desktop")
    observed_at: datetime = Field(default_factory=utcnow)

    results: list[dict] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    client_rank: int | None = None
    client_url: str | None = None
    raw_artifact_uri: str | None = None


class SerpExecution(TimestampedModel, table=True):
    """Usage & cost ledger for the (paid, external) SERP provider — mirrors
    ai_executions. Every SearchProvider.search() call produces exactly one
    row here, success or failure."""

    __tablename__ = "serp_executions"

    research_run_id: uuid.UUID | None = Field(default=None, foreign_key="research_runs.id", index=True)
    agent_run_id: uuid.UUID | None = Field(default=None, foreign_key="agent_runs.id", index=True)

    provider: str = Field(index=True)
    keyword: str
    country: str
    language: str

    cost_usd: float | None = None
    latency_ms: int | None = None
    status: SerpExecutionStatus = Field(default=SerpExecutionStatus.success)
    error: str | None = None
    raw_artifact_uri: str | None = None
