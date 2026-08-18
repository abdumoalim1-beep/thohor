import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel, utcnow


class RecommendationStatus(str, Enum):
    new = "new"
    planned = "planned"
    in_progress = "in_progress"
    implemented = "implemented"
    dismissed = "dismissed"
    superseded = "superseded"
    monitoring = "monitoring"
    successful = "successful"
    partial = "partial"
    no_detectable_impact = "no_detectable_impact"
    regressed = "regressed"
    # Beta Readiness Remediation — a previously-supported recommendation
    # whose evidence stopped holding up on a later run (e.g. topic-scope
    # re-check dropped every evidence_id). Never customer-visible while in
    # this status (same rule as a brand-new zero-evidence draft never
    # becoming a Recommendation at all) — see
    # app.opportunities.recommendation_engine.run_recommendation_engine.
    needs_validation = "needs_validation"


class Recommendation(TimestampedModel, table=True):
    """The specific, actionable step generated from a scored Opportunity
    (Group E2). Mutable status tracker like ResearchRun/AgentRun — updates
    in place on re-detection (matched by fingerprint), never duplicates;
    RecommendationHistory below is the append-only ledger of those updates.
    """

    __tablename__ = "recommendations"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    opportunity_id: uuid.UUID = Field(foreign_key="opportunities.id", index=True)
    first_seen_research_run_id: uuid.UUID = Field(foreign_key="research_runs.id")
    last_seen_research_run_id: uuid.UUID = Field(foreign_key="research_runs.id")

    title: str
    # Beta Readiness Remediation — the customer-facing structure from the
    # directive: WHAT WE FOUND (observed, evidence-grounded) is distinct
    # from WHAT TO IMPROVE (what_to_do, the suggested action) and WHY THIS
    # IMPROVEMENT (why_this_improvement, the reasoning connecting the two).
    # Never populate what_we_found with anything not directly traceable to
    # evidence_ids — that is exactly the discipline this remediation exists
    # to enforce structurally, not just by convention.
    what_we_found: str = ""
    what_to_do: str
    why_it_matters: str
    why_this_improvement: str = ""
    target_page: str | None = None
    page_id: uuid.UUID | None = Field(default=None, foreign_key="pages.id", index=True)
    product_id: uuid.UUID | None = Field(default=None, foreign_key="products.id", index=True)
    target_intents: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))

    evidence_ids: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    competitors_reference: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))

    expected_impact: float = Field(default=0.0)
    confidence: float = Field(default=0.0)
    # Deterministic tier derived from evidence quantity/diversity/finding
    # validation/cross-surface agreement (app.opportunities.confidence) —
    # never a free-floating AI opinion. "low" is excluded from the primary
    # queue by default (app.opportunities.freshness.select_primary_recommendations).
    confidence_tier: str = Field(default="medium")
    # What kind of claim what_to_do/implementation_package actually is:
    # "observed" — the suggested action is itself directly evidenced (e.g.
    # a missing_landing_page gap enumerated from a real competitor page);
    # "observed_with_best_practice" — the WHAT WE FOUND is evidenced, but
    # the specific implementation details (FAQ wording, schema types, H2
    # structure) are general best practice, not themselves evidence-derived
    # — never presented to the customer as a proven observation.
    claim_basis: str = Field(default="observed_with_best_practice")
    effort_estimate: str = Field(default="medium")
    priority_score: float = Field(default=0.0)

    implementation_steps: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    measurement_plan: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))
    implementation_package: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))

    status: RecommendationStatus = Field(default=RecommendationStatus.new)
    implementation_url: str | None = None
    implemented_at: datetime | None = None

    fingerprint: str = Field(index=True)
    updated_at: datetime = Field(default_factory=utcnow)


class RecommendationHistory(TimestampedModel, table=True):
    """Append-only: every time a recommendation is re-matched by fingerprint
    or its status changes, a new row here records what changed — the live
    Recommendation row is updated in place, but nothing here is ever
    overwritten or deleted (Group E design decision #6: 'لا نمسح التاريخ')."""

    __tablename__ = "recommendation_history"

    recommendation_id: uuid.UUID = Field(foreign_key="recommendations.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)
    event_type: str
    snapshot: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))
