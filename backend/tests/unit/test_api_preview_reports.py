"""API layer test — sqlite in-memory DB via dependency override, Celery
`.delay()` monkeypatched to a no-op, same convention as
tests/unit/test_api_stores.py. Verifies routing/request/response wiring
only — the pipeline itself is covered by test_preview_orchestration.py."""

import uuid
from datetime import datetime, timedelta, timezone

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


def test_create_preview_report_blocks_same_ip_within_cooldown(client, monkeypatch):
    test_client, _engine = client
    monkeypatch.setattr("app.api.preview_reports.execute_preview_report_task.delay", lambda *a, **k: None)

    first = test_client.post("/preview-reports", json={"store_url": "zuhoor.sa"})
    assert first.status_code == 200

    second = test_client.post("/preview-reports", json={"store_url": "another-store.sa"})
    assert second.status_code == 429
    assert second.json()["detail"]


def test_create_preview_report_allows_same_ip_after_cooldown(client, monkeypatch):
    test_client, engine = client
    monkeypatch.setattr("app.api.preview_reports.execute_preview_report_task.delay", lambda *a, **k: None)

    with Session(engine) as session:
        old_report = PreviewReport(
            store_url="https://old.sa",
            status="ready",
            ip_address="testclient",  # Starlette TestClient's fixed request.client.host
            created_at=datetime.now(timezone.utc) - timedelta(hours=49),
        )
        session.add(old_report)
        session.commit()

    response = test_client.post("/preview-reports", json={"store_url": "zuhoor.sa"})
    assert response.status_code == 200


def test_create_preview_report_ignores_a_different_ip(client, monkeypatch):
    test_client, engine = client
    monkeypatch.setattr("app.api.preview_reports.execute_preview_report_task.delay", lambda *a, **k: None)

    with Session(engine) as session:
        other_ip_report = PreviewReport(store_url="https://other.sa", status="ready", ip_address="203.0.113.5")
        session.add(other_ip_report)
        session.commit()

    response = test_client.post("/preview-reports", json={"store_url": "zuhoor.sa"})
    assert response.status_code == 200


def test_create_preview_report_bypass_token_skips_the_cooldown(client, monkeypatch):
    test_client, _engine = client
    monkeypatch.setattr("app.api.preview_reports.execute_preview_report_task.delay", lambda *a, **k: None)
    from app.core.config import Settings

    monkeypatch.setattr(
        "app.api.preview_reports.get_settings",
        lambda: Settings(preview_report_bypass_token="s3cr3t"),
    )

    first = test_client.post("/preview-reports", json={"store_url": "zuhoor.sa"})
    assert first.status_code == 200

    # without the header, the second call from the same IP is still blocked
    blocked = test_client.post("/preview-reports", json={"store_url": "another.sa"})
    assert blocked.status_code == 429

    # with the correct token, the cooldown is skipped entirely
    allowed = test_client.post(
        "/preview-reports", json={"store_url": "another.sa"}, headers={"X-Preview-Bypass": "s3cr3t"}
    )
    assert allowed.status_code == 200

    # a wrong token is not a bypass
    wrong_token = test_client.post(
        "/preview-reports", json={"store_url": "another.sa"}, headers={"X-Preview-Bypass": "nope"}
    )
    assert wrong_token.status_code == 429


def test_create_preview_report_prefers_x_forwarded_for_over_transport_ip(client, monkeypatch):
    """Render sits in front of the app as a proxy — request.client.host is
    always Render's own load-balancer address in production, never the
    visitor's, so the real IP must come from X-Forwarded-For instead (set
    by the proxy, first entry = the actual client)."""
    test_client, engine = client
    monkeypatch.setattr("app.api.preview_reports.execute_preview_report_task.delay", lambda *a, **k: None)

    response = test_client.post(
        "/preview-reports",
        json={"store_url": "zuhoor.sa"},
        headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"},
    )
    assert response.status_code == 200

    with Session(engine) as session:
        report = session.get(PreviewReport, uuid.UUID(response.json()["report_id"]))
        assert report.ip_address == "203.0.113.9"


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
