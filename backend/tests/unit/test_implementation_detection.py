from sqlmodel import select

from app.measurement.implementation_detection import detect_implementation
from app.models.catalog import Page
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.measurement import MeasurementBaseline
from app.models.observation import PageObservation
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import ResearchRun
from app.models.store import Store


def _make_scenario(session, *, before_extraction: dict | None, after_extraction: dict):
    org = Organization(name="t", slug="t-impl-detection")
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

    opportunity = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="missing_landing_page",
        title="t", description="d", status=OpportunityStatus.open, fingerprint="opp-fp",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    recommendation = Recommendation(
        store_id=store.id, opportunity_id=opportunity.id, first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id, title="t", what_to_do="do", why_it_matters="why",
        target_page="https://store.example/new-page", status=RecommendationStatus.new, fingerprint="rec-fp",
    )
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)

    session.add(
        MeasurementBaseline(
            recommendation_id=recommendation.id, research_run_id=run.id, page_metrics=before_extraction or {},
        )
    )
    session.commit()

    page = Page(store_id=store.id, url="https://store.example/new-page", page_type="content")
    session.add(page)
    session.commit()
    session.refresh(page)

    observation = PageObservation(
        store_id=store.id, research_run_id=run.id, page_id=page.id,
        source_url=page.url, source="crawler", extractor_version="v1",
        normalized_extraction=after_extraction, extracted_entities={},
    )
    session.add(observation)
    session.commit()
    session.refresh(observation)

    return store, recommendation, run, observation


def test_detect_implementation_marks_implemented_on_meaningful_change(session):
    before = {"title": "old", "h1": "old", "content_hash": "abc", "internal_links": [], "json_ld": []}
    after = {"title": "new title added", "h1": "new h1", "content_hash": "xyz", "internal_links": [], "json_ld": []}
    store, recommendation, run, observation = _make_scenario(session, before_extraction=before, after_extraction=after)

    change_set = detect_implementation(session, recommendation)

    assert change_set is not None
    assert change_set.has_meaningful_change() is True

    session.refresh(recommendation)
    assert recommendation.status == RecommendationStatus.implemented
    assert recommendation.implemented_at is not None

    evidence = session.exec(
        select(Evidence).where(Evidence.source_type == EvidenceSourceType.implementation_change_detection)
    ).all()
    assert len(evidence) == 1


def test_detect_implementation_leaves_status_unchanged_when_no_change(session):
    state = {"title": "t", "h1": "h", "content_hash": "abc", "internal_links": [], "json_ld": []}
    store, recommendation, run, observation = _make_scenario(
        session, before_extraction=state, after_extraction=dict(state)
    )

    change_set = detect_implementation(session, recommendation)

    assert change_set is not None
    assert change_set.has_meaningful_change() is False
    session.refresh(recommendation)
    assert recommendation.status == RecommendationStatus.new


def test_detect_implementation_returns_none_without_target_page(session):
    org = Organization(name="t", slug="t-impl-no-target")
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
    opportunity = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="google_visibility_gap",
        title="t", description="d", status=OpportunityStatus.open, fingerprint="opp-fp2",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)
    recommendation = Recommendation(
        store_id=store.id, opportunity_id=opportunity.id, first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id, title="t", what_to_do="do", why_it_matters="why",
        target_page=None, status=RecommendationStatus.new, fingerprint="rec-fp2",
    )
    session.add(recommendation)
    session.commit()

    assert detect_implementation(session, recommendation) is None
