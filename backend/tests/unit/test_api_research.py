import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
import app.models  # noqa: F401 — registers all tables
from app.core.db import get_session
from app.models.finding import Finding, FindingStatus
from app.models.org import Organization
from app.models.research import AgentRun, ResearchRun, RunStatus
from app.models.research_task import ResearchTask, TaskStatus, TaskType
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


def _seed_store_with_task_tree_and_findings(session):
    org = Organization(name="t", slug="t-api-research")
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

    root = ResearchTask(
        research_run_id=run.id,
        store_id=store.id,
        task_type=TaskType.competitor_discovery_batch,
        priority=1.0,
        depth=0,
        status=TaskStatus.completed,
        fingerprint="root-fp",
        result_summary="اكتشفنا منافسًا واحدًا",
        discovered_entities={"unique_competitors": 1},
    )
    session.add(root)
    session.commit()
    session.refresh(root)

    child = ResearchTask(
        research_run_id=run.id,
        parent_task_id=root.id,
        store_id=store.id,
        task_type=TaskType.competitor_deep_dive,
        priority=0.9,
        depth=1,
        status=TaskStatus.completed,
        fingerprint="child-fp",
        result_summary="وجدنا فجوة",
    )
    session.add(child)
    session.commit()

    finding = Finding(
        store_id=store.id,
        research_run_id=run.id,
        finding_type="dominant_competitor",
        statement="rival.test يهيمن على مجموعة أدوات القهوة",
        confidence=0.65,
        status=FindingStatus.candidate,
        validation_count=1,
    )
    session.add(finding)
    session.commit()

    agent_run = AgentRun(
        research_run_id=run.id,
        agent_type="iterative_research_agent_run",
        status=RunStatus.completed,
        findings={
            "total_tasks": 2,
            "search_queries_executed": 0,
            "ai_conversations_executed": 1,
            "pages_crawled": 0,
            "competitor_pages_analyzed": 1,
            "competitors_discovered": 1,
            "intents_discovered": 0,
            "new_queries_discovered": 0,
            "findings_generated": 1,
            "findings_validated": 0,
            "evidence_records": 1,
            "total_tokens": 100,
            "total_cost_usd": 0.01,
            "duration_seconds": 5.5,
            "research_depth_reached": 1,
        },
    )
    session.add(agent_run)
    session.commit()

    return store


def test_list_research_tasks_returns_tree_ordered_by_depth(client, db_session):
    store = _seed_store_with_task_tree_and_findings(db_session)

    response = client.get(f"/stores/{store.id}/research-tasks")

    assert response.status_code == 200
    body = response.json()
    assert len(body["tasks"]) == 2
    root, child = body["tasks"]
    assert root["depth"] == 0
    assert root["parent_task_id"] is None
    assert child["depth"] == 1
    assert child["parent_task_id"] == root["id"]
    assert child["task_type"] == "competitor_deep_dive"


def test_list_findings_returns_findings_for_latest_run(client, db_session):
    store = _seed_store_with_task_tree_and_findings(db_session)

    response = client.get(f"/stores/{store.id}/findings")

    assert response.status_code == 200
    body = response.json()
    assert len(body["findings"]) == 1
    assert body["findings"][0]["finding_type"] == "dominant_competitor"
    assert body["findings"][0]["status"] == "candidate"


def test_get_store_includes_research_summary(client, db_session):
    store = _seed_store_with_task_tree_and_findings(db_session)

    response = client.get(f"/stores/{store.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["research_summary"]["total_tasks"] == 2
    assert body["research_summary"]["research_depth_reached"] == 1


def test_list_research_tasks_404_for_unknown_store(client):
    response = client.get("/stores/00000000-0000-0000-0000-000000000000/research-tasks")
    assert response.status_code == 404


def test_list_findings_404_for_unknown_store(client):
    response = client.get("/stores/00000000-0000-0000-0000-000000000000/findings")
    assert response.status_code == 404
