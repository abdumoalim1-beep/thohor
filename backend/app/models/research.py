import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel


class ResearchRunType(str, Enum):
    baseline = "baseline"
    monitoring = "monitoring"
    discovery = "discovery"
    verification = "verification"


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    # Part H8 — a run whose iterative research loop stopped early because
    # cancellation was explicitly requested (see app.research.cancellation).
    # Distinct from `completed`: the fixed pipeline + whatever research had
    # already run still get to finish and produce a real (if smaller)
    # result, but the final status must say so honestly rather than reading
    # as a run that simply reached its natural conclusion.
    cancelled = "cancelled"


class ResearchRun(TimestampedModel, table=True):
    """Represents the whole task (e.g. 'Baseline run for store X').

    Orchestration sequencing/dependency logic lives in
    app/orchestrator/research_orchestrator.py, not here or in Celery tasks —
    this row is just the record of what happened.
    """

    __tablename__ = "research_runs"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    run_type: ResearchRunType = Field(default=ResearchRunType.baseline)
    status: RunStatus = Field(default=RunStatus.pending)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    # Part H2 (post-G-B directive) — which EvaluationMode this run actually
    # executed under (mock/replay/live), set once by the orchestrator at
    # execute_run() start and never changed after. Recorded on the run
    # itself (not just derived at summary-compute time) so it stays
    # queryable/visible anywhere the run is inspected, and so a replay run's
    # results are never mistakable for a fresh live measurement.
    evaluation_mode: str | None = None

    # Part H8 — set once, atomically (app.research.cancellation), when
    # cancellation is requested for a pending/running run. Deliberately
    # separate from `status`: the iterative loop polls this column directly
    # (a cheap scalar read) rather than trusting an in-memory `status` it
    # never re-reads from the DB, and the orchestrator uses it after the
    # loop returns to decide whether the final status should be
    # RunStatus.cancelled instead of RunStatus.completed.
    cancel_requested_at: datetime | None = None


class AgentRun(TimestampedModel, table=True):
    """A single independent step inside a research_run
    (crawl_agent_run, store_intelligence_agent_run, ai_classification_agent_run, ...).

    Output shape follows the Agent Contract (PRD section 43): structured,
    never free text.
    """

    __tablename__ = "agent_runs"

    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)
    agent_type: str = Field(index=True)
    status: RunStatus = Field(default=RunStatus.pending)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    findings: dict | None = Field(default=None, sa_column=Column(PortableJSONB))
    # Stored as strings, not UUID objects — SQLAlchemy's JSON column uses
    # plain json.dumps, which doesn't know how to serialize uuid.UUID.
    evidence_ids: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    confidence: float | None = None
    coverage: dict | None = Field(default=None, sa_column=Column(PortableJSONB))
    warnings: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    error: str | None = None
