from app.ai_visibility.cross_surface import compute_cross_surface_visibility
from app.models.ai_visibility import AIVisibilityObservation
from app.models.competitor import Competitor, CompetitorType
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
from app.models.stable_intent import StableIntent
from app.models.store import Store


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-cross-surface")
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


def test_compute_cross_surface_visibility_combines_google_and_ai_surfaces(session):
    store, run = _make_store_and_run(session)

    stable_intent = StableIntent(
        store_id=store.id, canonical_topic="grinder", normalized_topic="grinder", country="sa", language="ar",
        locale="sa_ar",
    )
    session.add(stable_intent)
    session.commit()
    session.refresh(stable_intent)

    competitor = Competitor(
        store_id=store.id, domain="rival.test", name="rival.test",
        competitor_type=CompetitorType.search_competitor, first_seen_research_run_id=run.id,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)

    # Google: we're absent, competitor is #1.
    import uuid

    session.add(
        SerpObservation(
            store_id=store.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id, keyword_id=uuid.uuid4(),
            research_run_id=run.id, country="sa", language="ar", client_rank=None,
            results=[{"rank": 1, "domain": "rival.test", "url": "https://rival.test/x"}],
        )
    )
    # ChatGPT: mentions us once out of two probes, mentions the competitor once.
    session.add(
        AIVisibilityObservation(
            store_id=store.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
            prompt_variant_id=uuid.uuid4(), research_run_id=run.id, surface="chatgpt", provider="openai",
            model="gpt-4o-mini", country="sa", language="ar", mentioned=True, competitors_mentioned=["rival.test"],
        )
    )
    session.add(
        AIVisibilityObservation(
            store_id=store.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
            prompt_variant_id=uuid.uuid4(), research_run_id=run.id, surface="chatgpt", provider="openai",
            model="gpt-4o-mini", country="sa", language="ar", mentioned=False, competitors_mentioned=[],
        )
    )
    session.commit()

    rows = compute_cross_surface_visibility(session, run.id)

    assert len(rows) == 1
    row = rows[0]
    assert row.topic == "grinder"
    assert row.store_visibility["google"] == 0.0
    assert row.store_visibility["chatgpt"] == 0.5
    assert row.competitor_visibility["rival.test"]["google"] == 1.0
    assert row.competitor_visibility["rival.test"]["chatgpt"] == 0.5


def test_compute_cross_surface_visibility_empty_run_returns_empty_list(session):
    store, run = _make_store_and_run(session)
    assert compute_cross_surface_visibility(session, run.id) == []


def test_compute_cross_surface_visibility_exposes_competitor_classification(session):
    """Part R6 — the frontend needs to know whether a domain that out-ranks
    the store (in competitor_visibility) is an actual business rival or
    something else (publisher, marketplace, ...), so it can frame that
    honestly instead of implying every domain shown is a competitor."""
    store, run = _make_store_and_run(session)
    stable_intent = StableIntent(
        store_id=store.id, canonical_topic="grinder", normalized_topic="grinder", country="sa", language="ar",
        locale="sa_ar",
    )
    session.add(stable_intent)
    session.commit()
    session.refresh(stable_intent)

    import uuid

    publisher = Competitor(
        store_id=store.id, domain="wikipedia.org", name="wikipedia.org",
        competitor_type=CompetitorType.search_competitor, first_seen_research_run_id=run.id,
        classification="publisher", classification_confidence=0.9,
    )
    session.add(publisher)
    session.commit()
    session.refresh(publisher)

    session.add(
        SerpObservation(
            store_id=store.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id, keyword_id=uuid.uuid4(),
            research_run_id=run.id, country="sa", language="ar", client_rank=None,
            results=[{"rank": 1, "domain": "wikipedia.org", "url": "https://wikipedia.org/x"}],
        )
    )
    session.commit()

    rows = compute_cross_surface_visibility(session, run.id)

    assert len(rows) == 1
    row = rows[0]
    assert row.competitor_visibility["wikipedia.org"]["google"] == 1.0
    assert row.competitor_classifications["wikipedia.org"] == "publisher"
