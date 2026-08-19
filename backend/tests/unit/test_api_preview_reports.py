"""API layer test — sqlite in-memory DB via dependency override, Celery
`.delay()` monkeypatched to a no-op, same convention as
tests/unit/test_api_stores.py. Verifies routing/request/response wiring
only — the pipeline itself is covered by test_preview_orchestration.py."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
import app.models  # noqa: F401 — registers all tables
from app.core.db import get_session
from app.models.preview_report import PreviewReport


@pytest.fixture()
def client():
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(test_engine)

    def override_get_session():
        with Session(test_engine) as session:
            yield session

    main_module.app.dependency_overrides[get_session] = override_get_session
    yield TestClient(main_module.app), test_engine
    main_module.app.dependency_overrides.clear()


def test_create_preview_report_dispatches_job_and_returns_processing(client, monkeypatch):
    test_client, _engine = client
    monkeypatch.setattr("app.api.preview_reports.execute_preview_report_task.delay", lambda *a, **k: None)

    response = test_client.post("/preview-reports", json={"store_url": "zuhoor.sa"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["report_id"]


def test_create_preview_report_rejects_empty_url(client, monkeypatch):
    test_client, _engine = client
    monkeypatch.setattr("app.api.preview_reports.execute_preview_report_task.delay", lambda *a, **k: None)

    response = test_client.post("/preview-reports", json={"store_url": "   "})
    assert response.status_code == 422


def test_get_processing_report_returns_no_blob(client, monkeypatch):
    test_client, engine = client
    monkeypatch.setattr("app.api.preview_reports.execute_preview_report_task.delay", lambda *a, **k: None)

    with Session(engine) as session:
        report = PreviewReport(store_url="https://zuhoor.sa", status="processing")
        session.add(report)
        session.commit()
        session.refresh(report)
        report_id = report.id

    response = test_client.get(f"/preview-reports/{report_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["report"] is None
    assert body["error_message"] is None


def test_get_ready_report_returns_the_full_blob(client):
    test_client, engine = client
    with Session(engine) as session:
        report = PreviewReport(
            store_url="https://zuhoor.sa", status="ready",
            report={"status": "ready", "store": {"brand_name": "زهور"}},
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        report_id = report.id

    response = test_client.get(f"/preview-reports/{report_id}")
    body = response.json()
    assert body["status"] == "ready"
    assert body["report"]["store"]["brand_name"] == "زهور"


def test_get_failed_report_returns_error_message_not_blob(client):
    test_client, engine = client
    with Session(engine) as session:
        report = PreviewReport(store_url="https://zuhoor.sa", status="failed", error_message="crawl timed out")
        session.add(report)
        session.commit()
        session.refresh(report)
        report_id = report.id

    response = test_client.get(f"/preview-reports/{report_id}")
    body = response.json()
    assert body["status"] == "failed"
    assert body["report"] is None
    assert body["error_message"] == "crawl timed out"


def test_get_unknown_report_404s(client):
    test_client, _engine = client
    import uuid

    response = test_client.get(f"/preview-reports/{uuid.uuid4()}")
    assert response.status_code == 404


def _join_payload(**overrides) -> dict:
    payload = {
        "name": "محمد",
        "email": "owner@zuhoor.sa",
        "report_feedback": "very_useful",
        "interest_level": "very_interested",
    }
    payload.update(overrides)
    return payload


def test_join_beta_persists_lead(client):
    test_client, engine = client
    with Session(engine) as session:
        report = PreviewReport(store_url="https://zuhoor.sa", status="ready", report={})
        session.add(report)
        session.commit()
        session.refresh(report)
        report_id = report.id

    response = test_client.post(f"/preview-reports/{report_id}/join", json=_join_payload())
    assert response.status_code == 200
    assert response.json()["id"]


def test_join_beta_rejects_empty_name(client):
    test_client, engine = client
    with Session(engine) as session:
        report = PreviewReport(store_url="https://zuhoor.sa", status="ready", report={})
        session.add(report)
        session.commit()
        session.refresh(report)
        report_id = report.id

    response = test_client.post(f"/preview-reports/{report_id}/join", json=_join_payload(name="  "))
    assert response.status_code == 422


def test_join_beta_rejects_missing_survey_answers(client):
    test_client, engine = client
    with Session(engine) as session:
        report = PreviewReport(store_url="https://zuhoor.sa", status="ready", report={})
        session.add(report)
        session.commit()
        session.refresh(report)
        report_id = report.id

    response = test_client.post(f"/preview-reports/{report_id}/join", json=_join_payload(interest_level=""))
    assert response.status_code == 422
