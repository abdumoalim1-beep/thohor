import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
import app.models  # noqa: F401 — registers all tables
from app.core.db import get_session
from app.models.ai_visibility import AIVisibilityObservation, PromptFamily, PromptVariant
from app.models.intent import Intent, IntentSource
from app.models.org import Organization
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


def _seed_store_with_observation(session):
    org = Organization(name="t", slug="t-api-ai-visibility")
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

    family = PromptFamily(intent_id=intent.id, research_run_id=run.id)
    session.add(family)
    session.commit()
    session.refresh(family)

    variant = PromptVariant(prompt_family_id=family.id, text="وش أفضل محمصة قهوة؟")
    session.add(variant)
    session.commit()
    session.refresh(variant)

    session.add(
        AIVisibilityObservation(
            store_id=store.id,
            intent_id=intent.id,
            prompt_variant_id=variant.id,
            research_run_id=run.id,
            provider="openai",
            model="gpt-4o-mini",
            country="sa",
            language="ar",
            mentioned=True,
            mention_position=5,
            citations=["https://roastinghouse.sa/x"],
            linked_domains=["roastinghouse.sa"],
        )
    )
    session.commit()

    return store


def test_list_ai_visibility_returns_summary_and_observations(client, db_session):
    store = _seed_store_with_observation(db_session)

    response = client.get(f"/stores/{store.id}/ai-visibility")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total_observations"] == 1
    assert body["summary"]["mention_rate"] == 1.0
    assert len(body["observations"]) == 1
    assert body["observations"][0]["intent_topic"] == "قهوة مختصة"
    assert body["observations"][0]["mentioned"] is True


def test_get_store_includes_ai_visibility_summary(client, db_session):
    store = _seed_store_with_observation(db_session)

    response = client.get(f"/stores/{store.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["ai_visibility_summary"]["total_observations"] == 1
    assert body["ai_visibility_summary"]["mention_rate"] == 1.0


def test_list_ai_visibility_404_for_unknown_store(client):
    response = client.get("/stores/00000000-0000-0000-0000-000000000000/ai-visibility")
    assert response.status_code == 404
