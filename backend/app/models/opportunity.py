import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel, utcnow


class OpportunityStatus(str, Enum):
    open = "open"
    actioned = "actioned"
    dismissed = "dismissed"
    expired = "expired"
    # Part Q2 — consolidated into another Opportunity that targets the same
    # underlying intent(s), rather than surfacing near-duplicate
    # customer-facing opportunities from different detectors. Never
    # deleted (same "keep it, mark why" principle as skipped_duplicate
    # research_tasks) — see app.opportunities.consolidation.
    merged = "merged"
    # Beta Readiness Remediation — "NO EVIDENCE → NO RECOMMENDATION": a real
    # research signal a detector found, but with no supporting Evidence
    # (typically an intent that was never actually queried this run). Kept
    # for internal traceability and future re-validation (a later run's
    # validate_finding/query_expansion task may supply real evidence), but
    # never promoted to a customer-visible Recommendation while in this
    # status — see app.opportunities.recommendation_engine.
    needs_validation = "needs_validation"


class Opportunity(TimestampedModel, table=True):
    """A commercial/research opportunity — distinct from a Finding (a raw
    research conclusion, Group D2) and a Recommendation (the specific
    actionable step, Group E3). opportunity_type and effort_estimate are
    plain strings, not a Postgres enum, so new detector types (Group E1)
    never need a manual ALTER TYPE migration to add — status is a real enum
    since that lifecycle is genuinely closed."""

    __tablename__ = "opportunities"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)

    opportunity_type: str = Field(index=True)
    title: str
    description: str

    affected_intents: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    affected_queries: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    affected_pages: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    affected_products: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    competitors: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    evidence_ids: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    finding_ids: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))

    google_visibility_gap: float = Field(default=0.0)
    ai_visibility_gap: float = Field(default=0.0)
    competitor_gap: float = Field(default=0.0)
    estimated_impact: float = Field(default=0.0)
    confidence: float = Field(default=0.0)
    effort_estimate: str = Field(default="medium")
    commercial_relevance: float = Field(default=0.0)

    priority_score: float = Field(default=0.0)
    score_breakdown: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))
    scoring_version: str = Field(default="v1")

    status: OpportunityStatus = Field(default=OpportunityStatus.open)
    fingerprint: str = Field(index=True)

    # Part Q2 — set only when status == merged; points at the surviving
    # Opportunity this one's evidence/findings were rolled into.
    merged_into_id: uuid.UUID | None = Field(default=None, foreign_key="opportunities.id", index=True)

    updated_at: datetime = Field(default_factory=utcnow)
