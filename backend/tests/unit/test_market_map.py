from app.competitors.market_map import compute_competitor_rankings
from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.intent import Intent, IntentSource
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-market-map")
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
    intent = Intent(
        store_id=store.id,
        research_run_id=run.id,
        topic="topic",
        country="sa",
        language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    return store, run, intent


def test_compute_competitor_rankings_orders_strongest_first(session):
    store, run, intent = _make_store_and_run(session)

    strong = Competitor(
        store_id=store.id,
        domain="strong.test",
        name="strong.test",
        competitor_type=CompetitorType.search_competitor,
        first_seen_research_run_id=run.id,
    )
    weak = Competitor(
        store_id=store.id,
        domain="weak.test",
        name="weak.test",
        competitor_type=CompetitorType.ai_recommendation_competitor,
        first_seen_research_run_id=run.id,
    )
    session.add(strong)
    session.add(weak)
    session.commit()
    session.refresh(strong)
    session.refresh(weak)

    session.add_all(
        [
            CompetitorRelationship(
                competitor_id=strong.id, intent_id=intent.id, research_run_id=run.id,
                source=RelationshipSource.serp, rank_or_position=1,
            ),
            CompetitorRelationship(
                competitor_id=strong.id, intent_id=intent.id, research_run_id=run.id,
                source=RelationshipSource.serp, rank_or_position=2,
            ),
            CompetitorRelationship(
                competitor_id=strong.id, intent_id=intent.id, research_run_id=run.id,
                source=RelationshipSource.ai_visibility, rank_or_position=1,
            ),
            CompetitorRelationship(
                competitor_id=weak.id, intent_id=intent.id, research_run_id=run.id,
                source=RelationshipSource.ai_visibility, rank_or_position=3,
            ),
        ]
    )
    session.commit()

    rankings = compute_competitor_rankings(session, run.id)

    assert len(rankings) == 2
    assert rankings[0].domain == "strong.test"
    assert rankings[0].serp_appearances == 2
    assert rankings[0].avg_serp_rank == 1.5
    assert rankings[0].ai_citation_count == 1

    assert rankings[1].domain == "weak.test"
    assert rankings[1].serp_appearances == 0
    assert rankings[1].avg_serp_rank is None
    assert rankings[1].ai_citation_count == 1


def test_compute_competitor_rankings_empty_when_no_relationships(session):
    store, run, intent = _make_store_and_run(session)
    assert compute_competitor_rankings(session, run.id) == []
