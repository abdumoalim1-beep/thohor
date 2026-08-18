from sqlmodel import select

from app.alerts.alert_engine import generate_alerts
from app.intent.intent_engine import _attach_keywords
from app.models.ai_visibility import AIVisibilityObservation
from app.models.base import utcnow
from app.models.competitor import Competitor, CompetitorType
from app.models.intent import Intent, IntentSource, Keyword
from app.models.measurement import MeasurementSnapshot
from app.models.stable_intent import StableIntent
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import ResearchRun, RunStatus
from app.models.serp import SerpObservation
from app.models.store import Store


def _make_store(session):
    org = Organization(name="t", slug="t-alert-engine")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


def _make_completed_run(session, store):
    run = ResearchRun(store_id=store.id, status=RunStatus.completed, started_at=utcnow(), completed_at=utcnow())
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _make_stable_intent(session, store, topic):
    stable_intent = StableIntent(
        store_id=store.id, canonical_topic=topic, normalized_topic=topic.lower(), country="sa", language="ar",
        locale="sa_ar",
    )
    session.add(stable_intent)
    session.commit()
    session.refresh(stable_intent)
    return stable_intent


def test_generate_alerts_empty_on_first_baseline_run(session):
    store = _make_store(session)
    run = _make_completed_run(session, store)
    alerts = generate_alerts(session, store, run)
    # No previous run -> competitor_overtook/ai_visibility_dropped/new_competitor never fire.
    assert not any(a.alert_type in ("competitor_overtook", "ai_visibility_dropped", "new_competitor") for a in alerts)


def test_detects_competitor_overtook_with_shared_intent(session):
    store = _make_store(session)
    previous_run = _make_completed_run(session, store)
    stable_intent = _make_stable_intent(session, store, "coffee grinder")
    intent = Intent(
        store_id=store.id, research_run_id=previous_run.id, stable_intent_id=stable_intent.id,
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
            research_run_id=previous_run.id,
            country="sa", language="ar", client_rank=2,
            results=[{"rank": 1, "domain": "rival.test", "url": "https://rival.test/x"}],
        )
    )
    session.commit()

    # A second run creates a brand-new Intent row (as real research runs do)
    # for the same real-world topic — sharing stable_intent_id is what
    # should let the alert match it against the previous run's observation.
    current_run = _make_completed_run(session, store)
    current_intent = Intent(
        store_id=store.id, research_run_id=current_run.id, stable_intent_id=stable_intent.id,
        topic="coffee grinder", country="sa", language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(current_intent)
    session.commit()
    session.refresh(current_intent)
    session.add(
        SerpObservation(
            store_id=store.id, intent_id=current_intent.id, stable_intent_id=stable_intent.id, keyword_id=keyword.id,
            research_run_id=current_run.id,
            country="sa", language="ar", client_rank=None,
            results=[{"rank": 1, "domain": "rival.test", "url": "https://rival.test/x"}],
        )
    )
    session.commit()

    alerts = generate_alerts(session, store, current_run)
    overtook = [a for a in alerts if a.alert_type == "competitor_overtook"]
    assert len(overtook) == 1
    assert "rival.test" in overtook[0].message


def test_detects_new_competitor_only_on_second_run(session):
    store = _make_store(session)
    previous_run = _make_completed_run(session, store)
    current_run = _make_completed_run(session, store)

    competitor = Competitor(
        store_id=store.id, domain="new-rival.test", name="new-rival.test",
        competitor_type=CompetitorType.search_competitor, first_seen_research_run_id=current_run.id,
    )
    session.add(competitor)
    session.commit()

    alerts = generate_alerts(session, store, current_run)
    new_competitor_alerts = [a for a in alerts if a.alert_type == "new_competitor"]
    assert len(new_competitor_alerts) == 1
    assert new_competitor_alerts[0].related_competitor_id == competitor.id


def test_detects_ai_visibility_dropped(session):
    store = _make_store(session)
    previous_run = _make_completed_run(session, store)
    intent = Intent(
        store_id=store.id, research_run_id=previous_run.id, topic="t", country="sa", language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    for i in range(4):
        session.add(
            AIVisibilityObservation(
                store_id=store.id, intent_id=intent.id, prompt_variant_id=intent.id,
                research_run_id=previous_run.id, provider="openai", model="gpt-4o-mini",
                country="sa", language="ar", mentioned=True,
            )
        )
    session.commit()

    current_run = _make_completed_run(session, store)
    for i in range(4):
        session.add(
            AIVisibilityObservation(
                store_id=store.id, intent_id=intent.id, prompt_variant_id=intent.id,
                research_run_id=current_run.id, provider="openai", model="gpt-4o-mini",
                country="sa", language="ar", mentioned=False,
            )
        )
    session.commit()

    alerts = generate_alerts(session, store, current_run)
    drop_alerts = [a for a in alerts if a.alert_type == "ai_visibility_dropped"]
    assert len(drop_alerts) == 1


def test_detects_recommendation_showing_results(session):
    store = _make_store(session)
    run = _make_completed_run(session, store)

    opportunity = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="google_visibility_gap",
        title="t", description="d", status=OpportunityStatus.open, fingerprint="opp-alert-fp",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    recommendation = Recommendation(
        store_id=store.id, opportunity_id=opportunity.id, first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id, title="أنشئ صفحة X", what_to_do="do", why_it_matters="why",
        status=RecommendationStatus.successful, fingerprint="rec-alert-fp",
    )
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)

    session.add(
        MeasurementSnapshot(recommendation_id=recommendation.id, research_run_id=run.id, google_visibility=0.8)
    )
    session.commit()

    alerts = generate_alerts(session, store, run)
    result_alerts = [a for a in alerts if a.alert_type == "recommendation_showing_results"]
    assert len(result_alerts) == 1
    assert result_alerts[0].related_recommendation_id == recommendation.id


def test_detects_new_high_priority_opportunity(session):
    store = _make_store(session)
    run = _make_completed_run(session, store)

    session.add(
        Opportunity(
            store_id=store.id, research_run_id=run.id, opportunity_type="google_visibility_gap",
            title="فرصة مهمة", description="d", priority_score=85.0,
            status=OpportunityStatus.open, fingerprint="opp-highprio-fp",
        )
    )
    session.commit()

    alerts = generate_alerts(session, store, run)
    priority_alerts = [a for a in alerts if a.alert_type == "new_high_priority_opportunity"]
    assert len(priority_alerts) == 1
