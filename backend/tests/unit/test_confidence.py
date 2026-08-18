import uuid

from app.models.evidence import Evidence, EvidenceSourceType
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.opportunities.confidence import compute_confidence

"""Beta Readiness Remediation, Section 6 — Recommendation Confidence Model.
Confidence must be derived deterministically from evidence properties
(quantity, source diversity, finding validation, competitor corroboration),
never a flat hand-set opinion. These tests pin down the exact tier
boundaries so a future change to compute_confidence has to consciously
decide to move them, not drift by accident."""


def _make_store_and_run(session):
    org = Organization(name="t", slug=f"t-confidence-{uuid.uuid4().hex[:8]}")
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


def _make_evidence(session, store, run, source_type=EvidenceSourceType.serp_observation, n=1):
    ids = []
    for _ in range(n):
        ev = Evidence(
            store_id=store.id, research_run_id=run.id, source_type=source_type,
            source_id=uuid.uuid4(), confidence=0.8, summary="test evidence",
        )
        session.add(ev)
        session.commit()
        session.refresh(ev)
        ids.append(str(ev.id))
    return ids


def test_single_uncorroborated_evidence_is_low_confidence(session):
    store, run = _make_store_and_run(session)
    evidence_ids = _make_evidence(session, store, run, n=1)

    result = compute_confidence(session, evidence_ids, finding_ids=[], competitors=[])

    assert result.tier == "low"
    assert result.evidence_count == 1


def test_single_evidence_backed_by_a_finding_is_at_least_medium(session):
    store, run = _make_store_and_run(session)
    evidence_ids = _make_evidence(session, store, run, n=1)

    result = compute_confidence(session, evidence_ids, finding_ids=["finding-1"], competitors=[])

    assert result.tier in ("medium", "high")


def test_three_or_more_evidence_links_is_high_confidence(session):
    store, run = _make_store_and_run(session)
    evidence_ids = _make_evidence(session, store, run, n=3)

    result = compute_confidence(session, evidence_ids, finding_ids=[], competitors=[])

    assert result.tier == "high"


def test_cross_surface_evidence_diversity_is_high_confidence_even_with_few_links(session):
    store, run = _make_store_and_run(session)
    evidence_ids = _make_evidence(session, store, run, source_type=EvidenceSourceType.serp_observation, n=1)
    evidence_ids += _make_evidence(session, store, run, source_type=EvidenceSourceType.ai_visibility_observation, n=1)

    result = compute_confidence(session, evidence_ids, finding_ids=[], competitors=[])

    assert result.source_diversity == 2
    assert result.tier == "high"


def test_finding_plus_competitor_corroboration_is_high_confidence_with_single_evidence(session):
    store, run = _make_store_and_run(session)
    evidence_ids = _make_evidence(session, store, run, n=1)

    result = compute_confidence(session, evidence_ids, finding_ids=["f-1"], competitors=["c-1"])

    assert result.tier == "high"


def test_zero_evidence_is_low_confidence_not_an_exception(session):
    """A caller inspecting a pre-gate draft (before run_recommendation_engine's
    NO EVIDENCE -> NO RECOMMENDATION check runs) must get a sane, clearly-low
    value rather than a crash — the actual invariant that zero-evidence never
    reaches a persisted Recommendation lives in recommendation_engine, not here."""
    store, run = _make_store_and_run(session)

    result = compute_confidence(session, [], finding_ids=[], competitors=[])

    assert result.tier == "low"
    assert result.confidence == 0.0
