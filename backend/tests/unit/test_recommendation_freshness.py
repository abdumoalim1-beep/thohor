"""Part R2 (Round 1 remediation) — recommendation freshness. Confirmed
root cause of the extra.com Overview bug: the primary queue was computed
from ALL status='new' recommendations ever created for a store, with no
check for whether the store's most recent completed run actually
reconfirmed them. A store whose latest run produced nothing valid still
showed old (in extra.com's case, pre-quality-gate-fix garbage)
recommendations as if they were current output."""

from sqlmodel import select

from app.models.base import utcnow
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import ResearchRun, RunStatus
from app.models.store import Store
from app.opportunities.freshness import (
    latest_completed_research_run_id,
    recommendation_freshness,
    select_primary_recommendations,
)


def _make_store(session):
    org = Organization(name="t", slug="t-freshness")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


def _make_completed_run(session, store):
    run = ResearchRun(store_id=store.id, status=RunStatus.completed, completed_at=utcnow())
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _make_recommendation(session, store, run, title, priority=80.0, status=RecommendationStatus.new):
    opp = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="google_visibility_gap",
        title=title, description="d", status=OpportunityStatus.open, fingerprint=f"opp-fp-{title}",
    )
    session.add(opp)
    session.commit()
    session.refresh(opp)

    rec = Recommendation(
        store_id=store.id, opportunity_id=opp.id, first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id, title=title, what_to_do="do", why_it_matters="why",
        priority_score=priority, status=status, fingerprint=f"rec-fp-{title}",
        evidence_ids=["ev-1"],  # a real recommendation is always evidence-backed (Part R8)
        # Beta Readiness Remediation — the primary queue now also requires
        # commercial relevance above PRIMARY_MIN_EXPECTED_IMPACT (0.4) and a
        # non-"low" confidence_tier; these tests are about freshness/staleness
        # semantics specifically, so give the fixture values that clear both
        # gates comfortably rather than accidentally exercising them here.
        expected_impact=0.7,
        confidence_tier="medium",
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def test_run_a_recommendation_is_current_right_after_run_a(session):
    store = _make_store(session)
    run_a = _make_completed_run(session, store)
    rec_x = _make_recommendation(session, store, run_a, "X")

    primary = select_primary_recommendations(session, store.id, max_size=5)

    assert [r.id for r in primary] == [rec_x.id]
    assert recommendation_freshness(rec_x, latest_completed_research_run_id(session, store.id)) == "current"


def test_run_b_producing_nothing_valid_means_run_a_recommendation_is_no_longer_current(session):
    """The exact extra.com scenario: Run B completes and finds nothing
    worth recommending (extra.com's 0 accepted intents). Run A's
    recommendation X must never be presented as Run B's current output."""
    store = _make_store(session)
    run_a = _make_completed_run(session, store)
    rec_x = _make_recommendation(session, store, run_a, "X")

    run_b = _make_completed_run(session, store)  # produces no recommendations at all

    primary = select_primary_recommendations(session, store.id, max_size=5)

    assert primary == []  # Run B found nothing -> the primary queue must be empty, not X
    assert recommendation_freshness(rec_x, latest_completed_research_run_id(session, store.id)) == "stale"


def test_run_c_replacement_is_current_and_original_is_no_longer_primary(session):
    """Run C produces an updated replacement for X (a fresh recommendation
    engine pass that reconfirms/regenerates it, moving
    last_seen_research_run_id forward, the normal fingerprint-matched
    update path) -- the latest version is current; had a run never
    reconfirmed X at all, it stays stale exactly like the Run B case."""
    store = _make_store(session)
    run_a = _make_completed_run(session, store)
    rec_x = _make_recommendation(session, store, run_a, "X")

    run_c = _make_completed_run(session, store)
    # Simulates run_recommendation_engine's fingerprint-matched update path:
    # same recommendation row, last_seen_research_run_id moves forward.
    rec_x.last_seen_research_run_id = run_c.id
    session.add(rec_x)
    session.commit()
    session.refresh(rec_x)

    primary = select_primary_recommendations(session, store.id, max_size=5)
    latest_id = latest_completed_research_run_id(session, store.id)

    assert [r.id for r in primary] == [rec_x.id]
    assert recommendation_freshness(rec_x, latest_id) == "current"


def test_superseded_recommendation_is_never_primary_regardless_of_freshness(session):
    store = _make_store(session)
    run = _make_completed_run(session, store)
    rec = _make_recommendation(session, store, run, "old-approach", status=RecommendationStatus.superseded)

    primary = select_primary_recommendations(session, store.id, max_size=5)

    assert primary == []
    assert recommendation_freshness(rec, latest_completed_research_run_id(session, store.id)) == "superseded"


def test_resolved_statuses_are_historical_not_stale(session):
    store = _make_store(session)
    run = _make_completed_run(session, store)
    rec = _make_recommendation(session, store, run, "done-and-measured", status=RecommendationStatus.successful)

    assert recommendation_freshness(rec, latest_completed_research_run_id(session, store.id)) == "historical"


def test_no_completed_run_at_all_means_empty_primary_queue(session):
    store = _make_store(session)
    pending_run = ResearchRun(store_id=store.id, status=RunStatus.running)
    session.add(pending_run)
    session.commit()
    session.refresh(pending_run)

    primary = select_primary_recommendations(session, store.id, max_size=5)

    assert primary == []


"""Beta Readiness Remediation, Section 7 — Primary Queue Quality. A
recommendation can be customer-visible (in the general list) without being
"do this now" material: low confidence_tier or low commercial relevance
excludes it from primary specifically, quality over quantity (fewer than
max_size returned is expected and correct when fewer recommendations
actually clear every gate)."""


def test_low_confidence_tier_recommendation_is_excluded_from_primary(session):
    store = _make_store(session)
    run = _make_completed_run(session, store)
    rec = _make_recommendation(session, store, run, "low-conf")
    rec.confidence_tier = "low"
    session.add(rec)
    session.commit()

    primary = select_primary_recommendations(session, store.id, max_size=5)

    assert primary == []


def test_low_commercial_relevance_recommendation_is_excluded_from_primary(session):
    store = _make_store(session)
    run = _make_completed_run(session, store)
    rec = _make_recommendation(session, store, run, "low-impact")
    rec.expected_impact = 0.1  # below PRIMARY_MIN_EXPECTED_IMPACT (0.4)
    session.add(rec)
    session.commit()

    primary = select_primary_recommendations(session, store.id, max_size=5)

    assert primary == []


def test_fewer_than_max_size_qualifying_recommendations_returns_fewer_not_padded(session):
    """Quality > quantity (Section 7): asking for 5 primaries when only 2
    genuinely qualify must return 2, never backfilled with weaker ones."""
    store = _make_store(session)
    run = _make_completed_run(session, store)
    good_a = _make_recommendation(session, store, run, "good-a", priority=90.0)
    good_b = _make_recommendation(session, store, run, "good-b", priority=80.0)
    weak = _make_recommendation(session, store, run, "weak-c", priority=70.0)
    weak.confidence_tier = "low"
    session.add(weak)
    session.commit()

    primary = select_primary_recommendations(session, store.id, max_size=5)

    assert [r.id for r in primary] == [good_a.id, good_b.id]
