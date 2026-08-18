"""Part Q2 — deterministic opportunity consolidation. No AI, no network —
ordinary state-based unit tests."""

from sqlmodel import select

from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.opportunities.consolidation import consolidate_opportunities


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-opp-consolidation")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    return store, run


def _make_opportunity(session, store, run, *, opportunity_type, affected_intents, priority_score=50.0, **overrides):
    defaults = dict(
        store_id=store.id, research_run_id=run.id, opportunity_type=opportunity_type,
        title=f"title-{opportunity_type}", description="desc", affected_intents=affected_intents,
        evidence_ids=[f"ev-{opportunity_type}"], finding_ids=[f"fd-{opportunity_type}"],
        competitors=[f"co-{opportunity_type}"], priority_score=priority_score, fingerprint=f"fp-{opportunity_type}-{id(affected_intents)}",
        status=OpportunityStatus.open,
    )
    defaults.update(overrides)
    opp = Opportunity(**defaults)
    session.add(opp)
    session.commit()
    session.refresh(opp)
    return opp


def test_opportunities_sharing_an_intent_merge_into_the_highest_priority_one(session):
    store, run = _make_store_and_run(session)
    intent_id = "intent-1"
    strong = _make_opportunity(
        session, store, run, opportunity_type="missing_landing_page", affected_intents=[intent_id],
        priority_score=80.0,
    )
    weak = _make_opportunity(
        session, store, run, opportunity_type="google_visibility_gap", affected_intents=[intent_id],
        priority_score=40.0,
    )

    survivors = consolidate_opportunities(session, store.id, run.id, [strong, weak])

    assert len(survivors) == 1
    assert survivors[0].id == strong.id
    session.refresh(strong)
    session.refresh(weak)
    assert strong.status == OpportunityStatus.open
    assert weak.status == OpportunityStatus.merged
    assert weak.merged_into_id == strong.id


def test_merged_opportunity_carries_the_union_of_evidence_and_competitors(session):
    store, run = _make_store_and_run(session)
    intent_id = "intent-1"
    a = _make_opportunity(
        session, store, run, opportunity_type="missing_landing_page", affected_intents=[intent_id],
        priority_score=80.0, evidence_ids=["ev-a"], finding_ids=["fd-a"], competitors=["co-a"],
    )
    b = _make_opportunity(
        session, store, run, opportunity_type="ai_citation_gap", affected_intents=[intent_id],
        priority_score=60.0, evidence_ids=["ev-b"], finding_ids=["fd-b"], competitors=["co-b"],
    )

    survivors = consolidate_opportunities(session, store.id, run.id, [a, b])

    assert len(survivors) == 1
    survivor = survivors[0]
    assert set(survivor.evidence_ids) == {"ev-a", "ev-b"}
    assert set(survivor.finding_ids) == {"fd-a", "fd-b"}
    assert set(survivor.competitors) == {"co-a", "co-b"}


def test_merged_opportunity_gap_dimensions_take_the_max_and_score_is_recomputed(session):
    store, run = _make_store_and_run(session)
    intent_id = "intent-1"
    a = _make_opportunity(
        session, store, run, opportunity_type="google_visibility_gap", affected_intents=[intent_id],
        priority_score=50.0, google_visibility_gap=0.3, ai_visibility_gap=0.0, estimated_impact=0.4,
        confidence=0.5, commercial_relevance=0.4, effort_estimate="medium",
    )
    b = _make_opportunity(
        session, store, run, opportunity_type="ai_citation_gap", affected_intents=[intent_id],
        priority_score=45.0, google_visibility_gap=0.1, ai_visibility_gap=0.9, estimated_impact=0.6,
        confidence=0.8, commercial_relevance=0.7, effort_estimate="medium",
    )

    survivors = consolidate_opportunities(session, store.id, run.id, [a, b])

    survivor = survivors[0]
    assert survivor.google_visibility_gap == 0.3
    assert survivor.ai_visibility_gap == 0.9  # max, not average — a strong signal is never diluted
    assert survivor.estimated_impact == 0.6
    assert survivor.confidence == 0.8
    assert survivor.commercial_relevance == 0.7
    # Recomputed, not just kept at the pre-merge value of 50.0 — the score
    # must reflect the merged (higher) gap dimensions.
    assert survivor.priority_score != 50.0
    assert survivor.score_breakdown["visibility_gap"] == 0.9


def test_opportunities_with_no_shared_intent_stay_separate(session):
    store, run = _make_store_and_run(session)
    a = _make_opportunity(
        session, store, run, opportunity_type="google_visibility_gap", affected_intents=["intent-1"],
    )
    b = _make_opportunity(
        session, store, run, opportunity_type="google_visibility_gap", affected_intents=["intent-2"],
    )

    survivors = consolidate_opportunities(session, store.id, run.id, [a, b])

    assert len(survivors) == 2
    session.refresh(a)
    session.refresh(b)
    assert a.status == OpportunityStatus.open
    assert b.status == OpportunityStatus.open


def test_opportunities_with_no_affected_intents_never_merge(session):
    """A category-level opportunity with no single affected_intents entry
    (empty list) never merges with anything — an empty set can't overlap."""
    store, run = _make_store_and_run(session)
    a = _make_opportunity(session, store, run, opportunity_type="category_visibility_gap", affected_intents=[])
    b = _make_opportunity(session, store, run, opportunity_type="category_visibility_gap", affected_intents=[])

    survivors = consolidate_opportunities(session, store.id, run.id, [a, b])

    assert len(survivors) == 2


def test_transitive_merging_across_three_opportunities(session):
    """A shares intent X with B; B shares intent Y (not X) with C. All
    three must end up in one merged group via B as the bridge."""
    store, run = _make_store_and_run(session)
    a = _make_opportunity(
        session, store, run, opportunity_type="missing_landing_page", affected_intents=["x"], priority_score=90.0,
    )
    b = _make_opportunity(
        session, store, run, opportunity_type="google_visibility_gap", affected_intents=["x", "y"],
        priority_score=50.0,
    )
    c = _make_opportunity(
        session, store, run, opportunity_type="ai_citation_gap", affected_intents=["y"], priority_score=40.0,
    )

    survivors = consolidate_opportunities(session, store.id, run.id, [a, b, c])

    assert len(survivors) == 1
    assert survivors[0].id == a.id
    session.refresh(b)
    session.refresh(c)
    assert b.merged_into_id == a.id
    assert c.merged_into_id == a.id


def test_already_merged_or_dismissed_opportunities_are_ignored(session):
    store, run = _make_store_and_run(session)
    open_one = _make_opportunity(
        session, store, run, opportunity_type="google_visibility_gap", affected_intents=["intent-1"],
    )
    already_dismissed = _make_opportunity(
        session, store, run, opportunity_type="ai_citation_gap", affected_intents=["intent-1"],
        status=OpportunityStatus.dismissed,
    )

    survivors = consolidate_opportunities(session, store.id, run.id, [open_one, already_dismissed])

    assert len(survivors) == 1
    assert survivors[0].id == open_one.id
    session.refresh(already_dismissed)
    assert already_dismissed.status == OpportunityStatus.dismissed  # untouched, not re-merged


def test_returns_survivors_sorted_by_priority_score_descending(session):
    store, run = _make_store_and_run(session)
    low = _make_opportunity(
        session, store, run, opportunity_type="google_visibility_gap", affected_intents=["a"], priority_score=20.0,
    )
    high = _make_opportunity(
        session, store, run, opportunity_type="ai_citation_gap", affected_intents=["b"], priority_score=90.0,
    )

    survivors = consolidate_opportunities(session, store.id, run.id, [low, high])

    assert [o.id for o in survivors] == [high.id, low.id]
