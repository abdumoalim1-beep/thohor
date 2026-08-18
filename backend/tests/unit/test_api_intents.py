import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
import app.models  # noqa: F401 — registers all tables
from app.core.db import get_session
from app.models.intent import Intent, IntentKeyword, IntentSource, Keyword
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
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


def _seed_store_with_intent(session):
    org = Organization(name="t", slug="t-api-intents")
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
        topic="عطور رجالية",
        category="عطور",
        country="sa",
        language="ar",
        confidence=1.0,
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    keyword = Keyword(text="عطور رجالية", country="sa", language="ar")
    session.add(keyword)
    session.commit()
    session.refresh(keyword)
    session.add(IntentKeyword(intent_id=intent.id, keyword_id=keyword.id, is_primary=True))
    session.commit()

    session.add(
        SerpObservation(
            store_id=store.id,
            intent_id=intent.id,
            keyword_id=keyword.id,
            research_run_id=run.id,
            country="sa",
            language="ar",
            results=[{"rank": 1, "domain": "store.example", "url": "https://store.example/x"}],
            client_rank=1,
            client_url="https://store.example/x",
        )
    )
    session.commit()

    return store, run


def test_list_intents_returns_keywords_and_serp_rank(client, db_session):
    store, _run = _seed_store_with_intent(db_session)

    response = client.get(f"/stores/{store.id}/intents")

    assert response.status_code == 200
    body = response.json()
    assert len(body["intents"]) == 1
    item = body["intents"][0]
    assert item["topic"] == "عطور رجالية"
    assert item["keywords"] == [{"text": "عطور رجالية", "is_primary": True}]
    assert item["client_rank"] == 1


def test_get_store_includes_intents_found_and_visibility_summary(client, db_session):
    store, _run = _seed_store_with_intent(db_session)

    response = client.get(f"/stores/{store.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["intents_found"] == 1
    assert body["visibility_summary"]["total_intents_measured"] == 1
    assert body["visibility_summary"]["ranking_coverage"] == 1.0
    assert body["visibility_summary"]["top3_rate"] == 1.0
