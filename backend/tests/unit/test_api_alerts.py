import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
import app.models  # noqa: F401 — registers all tables
from app.core.db import get_session
from app.models.alert import Alert, AlertStatus
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


def _seed_alert(session):
    org = Organization(name="t", slug="t-api-alerts")
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

    alert = Alert(
        store_id=store.id, research_run_id=run.id, alert_type="new_competitor", severity="info",
        title="منافس جديد", message="اكتشفنا منافسًا جديدًا", status=AlertStatus.unread,
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)

    return store, alert


def test_list_alerts_returns_alerts_for_store(client, db_session):
    store, alert = _seed_alert(db_session)
    response = client.get(f"/stores/{store.id}/alerts")
    assert response.status_code == 200
    body = response.json()["alerts"]
    assert len(body) == 1
    assert body[0]["alert_type"] == "new_competitor"
    assert body[0]["status"] == "unread"


def test_patch_alert_status_marks_read(client, db_session):
    store, alert = _seed_alert(db_session)
    response = client.patch(f"/alerts/{alert.id}/status", json={"status": "read"})
    assert response.status_code == 200
    assert response.json()["status"] == "read"


def test_patch_alert_status_rejects_invalid_status(client, db_session):
    store, alert = _seed_alert(db_session)
    response = client.patch(f"/alerts/{alert.id}/status", json={"status": "bogus"})
    assert response.status_code == 422


def test_list_alerts_404_for_unknown_store(client):
    response = client.get("/stores/00000000-0000-0000-0000-000000000000/alerts")
    assert response.status_code == 404


def test_patch_alert_404_for_unknown_alert(client, db_session):
    response = client.patch("/alerts/00000000-0000-0000-0000-000000000000/status", json={"status": "read"})
    assert response.status_code == 404
