from sqlmodel import select

from app.measurement.learning import compute_recommendation_type_stats
from app.models.measurement import MeasurementBaseline, MeasurementSnapshot
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import ResearchRun
from app.models.store import Store


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-learning")
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


def _make_resolved_recommendation(session, store, run, *, opportunity_type, status, google_before, google_after):
    opportunity = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type=opportunity_type,
        title="t", description="d", status=OpportunityStatus.open, fingerprint=f"opp-{opportunity_type}-{status.value}",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    recommendation = Recommendation(
        store_id=store.id, opportunity_id=opportunity.id, first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id, title="t", what_to_do="do", why_it_matters="why",
        status=status, fingerprint=f"rec-{opportunity_type}-{status.value}",
    )
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)

    session.add(MeasurementBaseline(recommendation_id=recommendation.id, research_run_id=run.id, google_visibility=google_before))
    session.add(MeasurementSnapshot(recommendation_id=recommendation.id, research_run_id=run.id, google_visibility=google_after))
    session.commit()

    return recommendation


def test_compute_recommendation_type_stats_across_terminal_recommendations(session):
    store, run = _make_store_and_run(session)
    _make_resolved_recommendation(session, store, run, opportunity_type="google_visibility_gap", status=RecommendationStatus.successful, google_before=0.0, google_after=0.3)
    _make_resolved_recommendation(session, store, run, opportunity_type="google_visibility_gap", status=RecommendationStatus.no_detectable_impact, google_before=0.2, google_after=0.2)
    # Non-terminal recommendation must be excluded entirely.
    non_terminal = Opportunity(store_id=store.id, research_run_id=run.id, opportunity_type="google_visibility_gap", title="t", description="d", status=OpportunityStatus.open, fingerprint="opp-nonterm")
    session.add(non_terminal)
    session.commit()
    session.refresh(non_terminal)
    session.add(Recommendation(store_id=store.id, opportunity_id=non_terminal.id, first_seen_research_run_id=run.id, last_seen_research_run_id=run.id, title="t", what_to_do="do", why_it_matters="why", status=RecommendationStatus.new, fingerprint="rec-nonterm"))
    session.commit()

    stats = compute_recommendation_type_stats(session)

    assert stats.sample_size == 2
    assert stats.success_rate == 0.5
    assert stats.avg_impact == 0.15  # (0.3 + 0.0) / 2
    assert stats.avg_time_to_impact_days is not None


def test_compute_recommendation_type_stats_filters_by_opportunity_type(session):
    store, run = _make_store_and_run(session)
    _make_resolved_recommendation(session, store, run, opportunity_type="google_visibility_gap", status=RecommendationStatus.successful, google_before=0.0, google_after=0.3)
    _make_resolved_recommendation(session, store, run, opportunity_type="ai_citation_gap", status=RecommendationStatus.regressed, google_before=0.3, google_after=0.1)

    stats = compute_recommendation_type_stats(session, opportunity_type="ai_citation_gap")

    assert stats.sample_size == 1
    assert stats.success_rate == 0.0


def test_compute_recommendation_type_stats_empty_when_no_terminal_recommendations(session):
    stats = compute_recommendation_type_stats(session)
    assert stats.sample_size == 0
    assert stats.success_rate is None
