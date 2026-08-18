import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel, utcnow


class FindingStatus(str, Enum):
    """Part G-B3 — candidate/validated/rejected keep their original DB
    values (no data-breaking rename) but are now read as hypothesis/
    validated/contradicted respectively. supported and insufficient_evidence
    are new: a finding checked against only one source can be meaningfully
    positive (supported) without yet clearing the multi-source bar for a
    full validated verdict, and a finding that's been checked but got a
    genuinely mixed/absent signal is insufficient_evidence, not silently
    stuck at candidate forever."""

    candidate = "candidate"  # hypothesis — not checked yet
    supported = "supported"  # one source checked, positive — not yet multi-source validated
    validated = "validated"  # 2+ independent sources agree
    rejected = "rejected"  # contradicted by evidence
    insufficient_evidence = "insufficient_evidence"  # checked, but signal is mixed or too weak either way


class Finding(TimestampedModel, table=True):
    """A synthesized claim about the market ('Competitor A dominates the
    office-perfumes cluster'), distinct from a raw Observation ('Competitor
    A ranked #2 for query X'). Findings start as candidates from
    deterministic rules (findings_engine.py — never AI, same 'AI is not
    Source of Truth' principle as everywhere else) and only become
    validated once independent sources agree (Part G-B3 —
    app/research/finding_validation.py), never from repeatedly re-checking
    the same source."""

    __tablename__ = "findings"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)

    # Part G-B4 — which research_task produced this finding, so a task's
    # downstream business impact (findings -> opportunities) can be traced
    # back to it (see app.research.findings_engine.backfill_task_opportunity_impact).
    # Null for findings that predate this field or aren't loop-task-driven.
    origin_task_id: uuid.UUID | None = Field(default=None, foreign_key="research_tasks.id", index=True)

    finding_type: str = Field(index=True)
    statement: str
    confidence: float = Field(default=0.5)

    # Part G-B3 — per-source verdicts (store/google/chatgpt/competitor_page
    # -> {checked, supports, detail}) and the human-readable rollup of them.
    # confidence is always derived from this, never set directly elsewhere.
    evidence_breakdown: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))
    confidence_explanation: str | None = None

    evidence_ids: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    affected_intents: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    affected_pages: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    affected_competitors: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))

    first_detected_at: datetime = Field(default_factory=utcnow)
    last_validated_at: datetime | None = None
    validation_count: int = Field(default=0)
    status: FindingStatus = Field(default=FindingStatus.candidate)
