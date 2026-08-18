import uuid
from datetime import datetime

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel, utcnow


class EvaluationSummary(TimestampedModel, table=True):
    """Part G0 — one row per evaluated research_run, so any future change
    to Planner/Prompt/Budget/Scoring/Competitor-filtering/Opportunity/
    Recommendation logic can be compared against a prior run's numbers
    instead of relying on impression. Computed after the fact from
    existing tables (research_orchestrator itself is untouched) — see
    app/evaluation/harness.py. Some G0-requested fields
    (competitors_accepted/rejected, duplicated/overlapping items) require
    classifiers that don't exist yet (Group G-B/G3/G4/G12/G13) and stay
    NULL until then — this table doesn't invent data it can't measure."""

    __tablename__ = "evaluation_summaries"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True, unique=True)

    store_url: str
    store_type: str | None = None  # Store.platform_hint / ai_classification business_type, whichever is set

    page_count: int
    research_tasks: int
    task_depth: int
    google_queries: int
    chatgpt_prompts: int
    total_observations: int

    competitors_discovered: int
    competitors_accepted: int | None = None  # deferred — no classifier yet (Group G-B)
    competitors_rejected: int | None = None  # deferred — no classifier yet (Group G-B)

    findings: int
    validated_findings: int

    opportunities: int
    recommendations: int
    primary_recommendations: int
    duplicated_or_overlapping_items: int | None = None  # deferred — no dedup analysis yet (Group G-C)

    ai_executions: int
    tokens: int
    cost_usd: float
    duration_seconds: float

    failures: int
    stop_reason: str

    research_yield: float | None = None  # validated_findings / research_tasks
    evidence_yield: float | None = None  # evidence referenced by this run's recommendations / total evidence this run

    # Part G-B — quality metrics beyond raw counts (G-B item 9). Filled in
    # progressively as each sub-phase ships the underlying classifier;
    # None means "not yet measurable", never a silent zero.
    intent_acceptance_rate: float | None = None  # accepted / (accepted + rejected) intents this run
    intent_duplicate_rate: float | None = None  # near-duplicate-rejected / total scored intents this run
    competitor_direct_count: int | None = None  # Part G-B2
    competitor_visibility_only_count: int | None = None  # Part G-B2
    competitor_irrelevant_rate: float | None = None  # Part G-B2
    finding_validation_rate: float | None = None  # validated_findings / findings
    dead_end_task_rate: float | None = None  # completed tasks with zero discovered_entities / completed tasks
    duplicate_task_proposal_rate: float | None = None  # skipped_duplicate / total proposed tasks
    recommendation_evidence_coverage: float | None = None  # recommendations with non-empty evidence_ids / recommendations

    versions: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))
    notes: str | None = None

    # Part H2 (post-G-B directive) — which EvaluationMode this run executed
    # under (mirrors ResearchRun.evaluation_mode at summary-compute time),
    # so a replay-sourced summary is never mistakable for a fresh live one.
    evaluation_mode: str | None = None

    # Concurrency/performance metrics (Part H — populated once the
    # concurrent orchestrator, H4, actually tracks them; None on any run
    # executed by the sequential loop, never a fake 0/1, since "ran
    # sequentially" and "ran concurrently but we didn't measure it" are
    # different facts).
    peak_concurrency: int | None = None
    average_concurrency: float | None = None
    provider_wait_time_seconds: float | None = None
    queue_wait_time_seconds: float | None = None
    rate_limit_events: int | None = None
    retry_count: int | None = None
    sequential_time_estimate_seconds: float | None = None
    actual_parallel_duration_seconds: float | None = None

    evaluated_at: datetime = Field(default_factory=utcnow)


class EvaluationCampaign(TimestampedModel, table=True):
    """Part H3 (post-G-B directive) — internal dev/evaluation tool only,
    never a product feature. Tracks real SerpAPI spend against an
    explicitly allocated budget for one of the three reserved live-
    validation rounds (FINAL_VALIDATION_1 / CORRECTION_VALIDATION /
    FINAL_BLIND_VALIDATION — plain string, not an enum, since this is an
    internal label nobody but the dev team ever sees) so a live round can
    never silently overspend the owner's remaining SerpAPI credits.
    `used_serp_requests` only increments through
    app.evaluation.campaign_guard.reserve_serp_request, which reserves
    capacity *before* a real request is dispatched, never after."""

    __tablename__ = "evaluation_campaigns"

    name: str = Field(index=True)
    allocated_serp_budget: int
    used_serp_requests: int = Field(default=0)
    stores: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    notes: str | None = None

    @property
    def remaining_budget(self) -> int:
        return max(0, self.allocated_serp_budget - self.used_serp_requests)
