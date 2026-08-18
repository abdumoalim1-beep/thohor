from sqlmodel import select

from app.intent.intent_engine import _attach_keywords, get_or_create_stable_intent
from app.measurement.baseline import capture_measurement_baseline
from app.measurement.monitoring_engine import run_monitoring_pass
from app.models.intent import Intent, IntentSource, Keyword
from app.models.measurement import MeasurementBaseline, MeasurementSnapshot
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
from app.models.stable_intent import StableIntent
from app.models.store import Store


def _make_store_intent_and_run(session, *, client_rank):
    org = Organization(name="t", slug="t-monitoring-engine")
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

    stable_intent = StableIntent(
        store_id=store.id, canonical_topic="coffee grinder", normalized_topic="coffee grinder", country="sa",
        language="ar", locale="sa_ar",
    )
    session.add(stable_intent)
    session.commit()
    session.refresh(stable_intent)

    intent = Intent(
        store_id=store.id, research_run_id=run.id, stable_intent_id=stable_intent.id,
        topic="coffee grinder", country="sa", language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    _attach_keywords(session, intent, ["coffee grinder"], "sa", "ar")
    keyword = session.exec(select(Keyword)).one()

    session.add(
        SerpObservation(
            store_id=store.id, intent_id=intent.id, stable_intent_id=stable_intent.id, keyword_id=keyword.id,
            research_run_id=run.id,
            country="sa", language="ar", results=[], client_rank=client_rank,
        )
    )
    session.commit()

    return store, intent, run


def _make_recommendation(session, store, intent, run, *, status, google_visibility_baseline):
    opportunity = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="google_visibility_gap",
        title="t", description="d", status=OpportunityStatus.open, fingerprint="opp-fp-mon",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    recommendation = Recommendation(
        store_id=store.id, opportunity_id=opportunity.id, first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id, title="t", what_to_do="do", why_it_matters="why",
        target_intents=[str(intent.stable_intent_id)], status=status, fingerprint="rec-fp-mon",
    )
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)

    session.add(
        MeasurementBaseline(
            recommendation_id=recommendation.id, research_run_id=run.id,
            target_queries=[{"stable_intent_id": str(intent.stable_intent_id)}], google_visibility=google_visibility_baseline,
        )
    )
    session.commit()

    return recommendation


async def test_run_monitoring_pass_transitions_implemented_to_successful(session):
    # Baseline: weak (client_rank None -> 0.0). This run: strong (rank 1 -> 1.0). Big improvement.
    store, intent, run = _make_store_intent_and_run(session, client_rank=1)
    recommendation = _make_recommendation(
        session, store, intent, run, status=RecommendationStatus.implemented, google_visibility_baseline=0.0
    )

    summary = await run_monitoring_pass(session, store, run.id)

    assert summary["snapshots_taken"] == 1
    assert summary["outcomes_classified"] == 1

    session.refresh(recommendation)
    assert recommendation.status == RecommendationStatus.successful

    snapshots = session.exec(
        select(MeasurementSnapshot).where(MeasurementSnapshot.recommendation_id == recommendation.id)
    ).all()
    assert len(snapshots) == 1
    assert snapshots[0].google_visibility == 1.0


async def test_run_monitoring_pass_skips_when_intent_not_remeasured_this_run(session):
    store, intent, run = _make_store_intent_and_run(session, client_rank=None)
    # Delete the SerpObservation so this run has no fresh data for the intent.
    from app.models.serp import SerpObservation as SO

    for obs in session.exec(select(SO)).all():
        session.delete(obs)
    session.commit()

    recommendation = _make_recommendation(
        session, store, intent, run, status=RecommendationStatus.monitoring, google_visibility_baseline=0.5
    )

    summary = await run_monitoring_pass(session, store, run.id)

    assert summary["snapshots_taken"] == 0
    session.refresh(recommendation)
    assert recommendation.status == RecommendationStatus.monitoring  # unchanged, still waiting for data


async def test_run_monitoring_pass_leaves_non_eligible_recommendations_alone(session):
    store, intent, run = _make_store_intent_and_run(session, client_rank=1)
    recommendation = _make_recommendation(
        session, store, intent, run, status=RecommendationStatus.dismissed, google_visibility_baseline=0.0
    )

    summary = await run_monitoring_pass(session, store, run.id)

    assert summary["recommendations_monitored"] == 0
    session.refresh(recommendation)
    assert recommendation.status == RecommendationStatus.dismissed


async def test_stable_intent_identity_enables_cross_run_monitoring_snapshot(session):
    """Part F.5-0 regression — the exact scenario Group F flagged as a known
    limitation: Run A creates an Intent + Recommendation + baseline. Run B
    regenerates an *equivalent* Intent (new UUID, same real-world topic —
    exactly what a real research run does) with fresh SERP observations.
    Before stable_intent_id existed, measure_visibility_for_intents matched
    on the run-scoped intent_id and could never find Run B's observations,
    so monitoring silently produced zero snapshots forever. It must now
    find them via stable_intent_id."""
    org = Organization(name="t", slug="t-stable-intent-monitoring")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)

    # --- Run A: create intent, recommendation, baseline ---
    run_a = ResearchRun(store_id=store.id)
    session.add(run_a)
    session.commit()
    session.refresh(run_a)

    stable_intent = get_or_create_stable_intent(
        session, store_id=store.id, topic="coffee grinder", country="sa", language="ar"
    )
    intent_a = Intent(
        store_id=store.id, research_run_id=run_a.id, stable_intent_id=stable_intent.id,
        topic="coffee grinder", country="sa", language="ar", source=IntentSource.deterministic_catalog,
    )
    session.add(intent_a)
    session.commit()
    session.refresh(intent_a)
    _attach_keywords(session, intent_a, ["coffee grinder"], "sa", "ar")
    keyword = session.exec(select(Keyword).where(Keyword.text == "coffee grinder")).one()

    session.add(
        SerpObservation(
            store_id=store.id, intent_id=intent_a.id, stable_intent_id=stable_intent.id, keyword_id=keyword.id,
            research_run_id=run_a.id, country="sa", language="ar", results=[], client_rank=None,
        )
    )
    session.commit()

    opportunity = Opportunity(
        store_id=store.id, research_run_id=run_a.id, opportunity_type="google_visibility_gap",
        title="t", description="d", status=OpportunityStatus.open, fingerprint="opp-fp-stable-cross-run",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    recommendation = Recommendation(
        store_id=store.id, opportunity_id=opportunity.id, first_seen_research_run_id=run_a.id,
        last_seen_research_run_id=run_a.id, title="t", what_to_do="do", why_it_matters="why",
        target_intents=[str(stable_intent.id)], status=RecommendationStatus.implemented,
        fingerprint="rec-fp-stable-cross-run",
    )
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)

    baseline = capture_measurement_baseline(session, recommendation, run_a.id)
    assert baseline.google_visibility == 0.0  # absent from results -> weak

    # --- Run B: monitoring pass, a regenerated Intent for the same topic ---
    run_b = ResearchRun(store_id=store.id)
    session.add(run_b)
    session.commit()
    session.refresh(run_b)

    same_stable_intent = get_or_create_stable_intent(
        session, store_id=store.id, topic="coffee grinder", country="sa", language="ar"
    )
    assert same_stable_intent.id == stable_intent.id  # same real-world topic -> same stable identity

    intent_b = Intent(
        store_id=store.id, research_run_id=run_b.id, stable_intent_id=same_stable_intent.id,
        topic="coffee grinder", country="sa", language="ar", source=IntentSource.deterministic_catalog,
    )
    session.add(intent_b)
    session.commit()
    session.refresh(intent_b)
    assert intent_b.id != intent_a.id  # genuinely a new run-scoped Intent row, new UUID

    session.add(
        SerpObservation(
            store_id=store.id, intent_id=intent_b.id, stable_intent_id=same_stable_intent.id, keyword_id=keyword.id,
            research_run_id=run_b.id, country="sa", language="ar", results=[], client_rank=1,
        )
    )
    session.commit()

    summary = await run_monitoring_pass(session, store, run_b.id)

    assert summary["snapshots_taken"] > 0
    snapshots = session.exec(
        select(MeasurementSnapshot).where(MeasurementSnapshot.recommendation_id == recommendation.id)
    ).all()
    assert len(snapshots) == 1
    assert snapshots[0].google_visibility == 1.0

    session.refresh(recommendation)
    assert recommendation.status == RecommendationStatus.successful
