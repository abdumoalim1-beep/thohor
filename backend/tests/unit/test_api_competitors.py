import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
import app.models  # noqa: F401 — registers all tables
from app.core.db import get_session
from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.intent import Intent, IntentSource
from app.models.org import Organization
from app.models.page_intelligence import PageGapAnalysis
from app.models.research import ResearchRun
from app.models.store import Store


@pytest.fixture()
def db_session():
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(test_engine)

    def override_get_session():
        with Session(test_engine) as session:
            yield session

    main_module.app.dependency_overrides[get_session] = override_get_session
    with Session(test_engine) as session:
        yield session
    main_module.app.dependency_overrides.clear()


@pytest.fixture()
def client(db_session):
    return TestClient(main_module.app)


def _seed_store_with_competitor_and_gap(session):
    org = Organization(name="t", slug="t-api-competitors")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://roastinghouse.sa")
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
        topic="قهوة مختصة",
        country="sa",
        language="ar",
        confidence=1.0,
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    competitor = Competitor(
        store_id=store.id,
        domain="rival-roastery.test",
        name="rival-roastery.test",
        competitor_type=CompetitorType.search_competitor,
        first_seen_research_run_id=run.id,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)

    session.add(
        CompetitorRelationship(
            competitor_id=competitor.id,
            intent_id=intent.id,
            research_run_id=run.id,
            source=RelationshipSource.serp,
            rank_or_position=1,
        )
    )
    session.commit()

    gap = PageGapAnalysis(
        store_id=store.id,
        intent_id=intent.id,
        competitor_id=competitor.id,
        research_run_id=run.id,
        competitor_url="https://rival-roastery.test/guide",
        gaps=["دليل تحميص القهوة غير موجود عندنا"],
        recommendation_summary="أضف دليل تحميص القهوة.",
        confidence=0.7,
    )
    session.add(gap)
    session.commit()

    return store


def test_list_competitors_returns_ranked_competitors(client, db_session):
    store = _seed_store_with_competitor_and_gap(db_session)

    response = client.get(f"/stores/{store.id}/competitors")

    assert response.status_code == 200
    body = response.json()
    assert len(body["competitors"]) == 1
    assert body["competitors"][0]["domain"] == "rival-roastery.test"
    assert body["competitors"][0]["serp_appearances"] == 1
    assert body["competitors"][0]["avg_serp_rank"] == 1


def test_list_page_gaps_returns_gap_with_intent_and_competitor(client, db_session):
    store = _seed_store_with_competitor_and_gap(db_session)

    response = client.get(f"/stores/{store.id}/page-gaps")

    assert response.status_code == 200
    body = response.json()
    assert len(body["page_gaps"]) == 1
    gap = body["page_gaps"][0]
    assert gap["intent_topic"] == "قهوة مختصة"
    assert gap["competitor_domain"] == "rival-roastery.test"
    assert "دليل تحميص القهوة غير موجود عندنا" in gap["gaps"]


def test_get_store_includes_competitors_found(client, db_session):
    store = _seed_store_with_competitor_and_gap(db_session)

    response = client.get(f"/stores/{store.id}")

    assert response.status_code == 200
    assert response.json()["competitors_found"] == 1


def test_list_competitors_404_for_unknown_store(client):
    response = client.get("/stores/00000000-0000-0000-0000-000000000000/competitors")
    assert response.status_code == 404


def test_list_page_gaps_404_for_unknown_store(client):
    response = client.get("/stores/00000000-0000-0000-0000-000000000000/page-gaps")
    assert response.status_code == 404
