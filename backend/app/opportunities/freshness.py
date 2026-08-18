import uuid

from sqlmodel import Session, select
from sqlalchemy.orm import defer

from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import ResearchRun, ResearchRunType, RunStatus
from app.opportunities.quality_gate import check_recommendation_batch_quality

# Beta Readiness Remediation, Section 7 — commercial_relevance floor for the
# primary queue specifically. Mirrors detectors.MIN_INTENT_CONFIDENCE (0.4),
# the same floor already used upstream to decide an intent is worth an
# opportunity at all — a recommendation whose expected_impact fell below
# that bar going into scoring shouldn't be promoted to "do this now" either.
PRIMARY_MIN_EXPECTED_IMPACT = 0.4
# Quality-gate check names (app.opportunities.quality_gate.QualityIssue.check)
# that disqualify a recommendation from the primary queue specifically —
# actionability (generic_advice, raw_page_title) and duplication. Kept
# separate from the general list: a generic or near-duplicate recommendation
# still exists and is still visible in the store's full list (it may be the
# only thing found for that store this run), it just never gets to be one of
# the "do this now" top picks.
_PRIMARY_DISQUALIFYING_CHECKS = frozenset({"generic_advice", "raw_page_title", "duplicate_recommendation", "unsupported_claim"})

# Part R2 (Round 1 remediation) — statuses that mean the recommendation's
# lifecycle has already concluded one way or another (implemented and
# measured, or explicitly dismissed). These are never "current action
# items" regardless of which run last touched them.
_RESOLVED_STATUSES = frozenset(
    {
        RecommendationStatus.implemented,
        RecommendationStatus.successful,
        RecommendationStatus.partial,
        RecommendationStatus.no_detectable_impact,
        RecommendationStatus.regressed,
        RecommendationStatus.dismissed,
    }
)


def latest_completed_research_run_id(session: Session, store_id: uuid.UUID) -> uuid.UUID | None:
    run = session.exec(
        select(ResearchRun)
        .where(ResearchRun.store_id == store_id)
        .where(ResearchRun.status == RunStatus.completed)
        .where(ResearchRun.run_type != ResearchRunType.discovery)
        .order_by(ResearchRun.completed_at.desc())  # type: ignore[arg-type]
    ).first()
    return run.id if run is not None else None


def recommendation_freshness(recommendation: Recommendation, latest_completed_run_id: uuid.UUID | None) -> str:
    """Part R2 — the exact freshness split the directive asked for:
    CURRENT / STALE / HISTORICAL / SUPERSEDED. Orthogonal to `status`
    (lifecycle stage) — a `new` recommendation can be either current or
    stale depending purely on whether the store's most recent completed
    run actually reconfirmed it (last_seen_research_run_id). No new schema:
    last_seen_research_run_id already carries exactly the signal needed."""
    if recommendation.status == RecommendationStatus.superseded:
        return "superseded"
    if recommendation.status in _RESOLVED_STATUSES:
        return "historical"
    if latest_completed_run_id is not None and recommendation.last_seen_research_run_id == latest_completed_run_id:
        return "current"
    return "stale"


def select_primary_recommendations(
    session: Session, store_id: uuid.UUID, max_size: int, *, as_of_run_id: uuid.UUID | None = None
) -> list[Recommendation]:
    """The one place 'what belongs in the primary queue' is decided —
    Part R2: a recommendation not reconfirmed by the reference run
    (`as_of_run_id`, defaulting to the store's most recent completed run —
    the right default for customer-facing reads) must never be selected as
    primary, no matter how high its priority_score. That is exactly what
    let Round 1's extra.com show pre-fix garbage recommendations as if
    they were current-run output. Callers evaluating a *specific* past run
    (e.g. the benchmark harness recomputing an older run's summary) pass
    that run's id explicitly instead of silently comparing against
    whatever the latest run happens to be today. Callers needing the
    historical/stale set for a separate, clearly-labeled section can
    compute it via recommendation_freshness() on the full list themselves;
    this function only ever returns current, actionable recommendations."""
    reference_run_id = as_of_run_id if as_of_run_id is not None else latest_completed_research_run_id(session, store_id)
    if reference_run_id is None:
        return []

    candidates = session.exec(
        select(Recommendation)
        .options(defer(Recommendation.page_id), defer(Recommendation.product_id))
        .where(Recommendation.store_id == store_id)
        .where(Recommendation.status == RecommendationStatus.new)
        .where(Recommendation.last_seen_research_run_id == reference_run_id)
        .order_by(Recommendation.priority_score.desc())  # type: ignore[arg-type]
    ).all()
    # Part R8 / Beta Readiness Remediation Section 7 — "quality over
    # quantity, and only what actually clears every gate becomes primary":
    # evidence_ids non-empty is now a structural guarantee for any
    # persisted Recommendation (app.opportunities.recommendation_engine
    # never creates or keeps one with empty evidence — see
    # OpportunityStatus.needs_validation), kept here anyway as a
    # defense-in-depth check rather than trusting that invariant blindly.
    # confidence_tier == "low" and commercial relevance below the floor are
    # excluded from primary specifically (Section 6/7) — they may still
    # appear in the store's general recommendation list, just never as a
    # "do this now" pick. Near-duplicate/generic/raw-title issues
    # (check_recommendation_batch_quality, Part Q3) were previously
    # report-only; enforced here now so a failing check actually removes a
    # recommendation from the primary queue instead of only being logged.
    disqualified_ids = {
        issue.recommendation_id
        for issue in check_recommendation_batch_quality(candidates)
        if issue.check in _PRIMARY_DISQUALIFYING_CHECKS
    }
    qualified = [
        r
        for r in candidates
        if r.evidence_ids
        and r.confidence_tier != "low"
        and r.expected_impact >= PRIMARY_MIN_EXPECTED_IMPACT
        and r.id not in disqualified_ids
    ]
    return qualified[:max_size]
