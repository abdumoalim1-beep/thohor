"""Regression test for a real bug caught during live verification of the
90-search re-scope: GET /stores/{id}/visibility-runs/latest's in-flight
branch picked whichever 'running' VisibilityRun row the DB happened to
return first (no order_by), which is normally harmless (at most one
running row exists, guarded by the trigger endpoint's 409) but a worker
crash/restart mid-task can leave an older stuck row behind a newer,
actually-progressing one — confirmed live when a celery worker restart
produced exactly this. The fix orders by started_at desc so the poll
always reflects the most recently started run."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.main as main_module
import app.models  # noqa: F401 — registers all tables
from app.core.db import get_session
from app.models.base import utcnow
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.models.visibility_run import EngineAnswer, VisibilityQuestion, VisibilityRun


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


def _make_store(session):
    org = Organization(name="t", slug="t-visibility-progress")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://flowery.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


def test_in_flight_poll_reflects_the_most_recently_started_run_not_an_older_stuck_one(client, db_session):
    store = _make_store(db_session)

    stuck = VisibilityRun(
        store_id=store.id, status="running", total_operations_planned=0, started_at=utcnow() - timedelta(minutes=10)
    )
    db_session.add(stuck)
    db_session.commit()

    active = VisibilityRun(store_id=store.id, status="running", total_operations_planned=90)
    db_session.add(active)
    db_session.commit()
    db_session.refresh(active)
    for _ in range(37):
        db_session.add(EngineAnswer(
            visibility_run_id=active.id, question_id=store.id, store_id=store.id,
            engine="chatgpt", engine_model="gpt-4o-mini", status="success", raw_answer="x",
        ))
    db_session.commit()

    response = client.get(f"/stores/{store.id}/visibility-runs/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["run_id"] == str(active.id)
    assert body["completed_count"] == 37
    assert body["total_planned"] == 90


def test_trigger_refuses_to_start_when_no_questions_exist_yet(client, db_session):
    """Real bug caught live: /signup's auto-trigger fires the instant
    understanding_stage goes 'ready', which happens right after identity
    resolves — a full step *before* question generation (later in the same
    baseline research run) has produced anything. Triggering anyway used to
    silently create a run that completed instantly with 0 questions
    measured — indistinguishable from 'finished, nothing to show'. The
    endpoint must now refuse (not_ready) instead of creating a wasted run."""
    store = _make_store(db_session)

    response = client.post(f"/stores/{store.id}/visibility-runs")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["visibility_run_id"] is None
    # No run was created at all — a caller polling /latest still sees "no run yet".
    assert db_session.exec(select(VisibilityRun).where(VisibilityRun.store_id == store.id)).first() is None


def test_trigger_starts_a_real_run_once_questions_exist(client, db_session, monkeypatch):
    monkeypatch.setattr("app.api.visibility.execute_visibility_run_task.delay", lambda *a, **k: None)
    store = _make_store(db_session)
    run = ResearchRun(store_id=store.id)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    db_session.add(VisibilityQuestion(
        store_id=store.id, text="سؤال", category="best", normalized_text="سؤال", source_research_run_id=run.id,
    ))
    db_session.commit()

    response = client.post(f"/stores/{store.id}/visibility-runs")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["visibility_run_id"] is not None
