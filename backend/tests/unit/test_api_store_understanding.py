"""API layer tests for the progressive "فهمنا متجرك" endpoints: same
sqlite in-memory fixture pattern as test_api_stores.py — verifies routing
and the understanding_stage state machine, not the crawler itself.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
import app.models  # noqa: F401 — registers all tables
from app.core.db import get_session
from app.models.catalog import Brand, Category, Page, Product
from app.models.observation import PageObservation
from app.models.research import AgentRun, ResearchRun, RunStatus


@pytest.fixture()
def client():
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(test_engine)

    def override_get_session():
        with Session(test_engine) as session:
            yield session

    main_module.app.dependency_overrides[get_session] = override_get_session
    yield TestClient(main_module.app)
    main_module.app.dependency_overrides.clear()


def _create_store(client, monkeypatch, url="https://sonay.sa"):
    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    created = client.post("/stores", json={"url": url}).json()
    return uuid.UUID(created["store_id"]), uuid.UUID(created["research_run_id"])


def _session():
    override = main_module.app.dependency_overrides[get_session]
    return next(override())


def test_understanding_is_pending_before_any_run_exists(client, monkeypatch):
    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    store_id = uuid.uuid4()
    # No store created at all — 404 path covered separately; here we cover a
    # store that exists but whose run has no agent_runs yet (fresh pending).
    client.post("/stores", json={"url": "https://example.com"})
    store_id, _run_id = _create_store(client, monkeypatch, url="https://freshstore.com")

    response = client.get(f"/stores/{store_id}/understanding")

    assert response.status_code == 200
    body = response.json()
    assert body["understanding_stage"] == "pending"
    assert body["business_type"] is None
    assert body["top_categories"] == []
    assert body["product_samples"] == []


def test_understanding_is_partial_once_crawl_completes_but_classification_still_running(client, monkeypatch):
    store_id, run_id = _create_store(client, monkeypatch)
    session = _session()
    session.add(Product(store_id=store_id, name="كوب قهوة", url="https://sonay.sa/p/1"))
    session.add(Category(store_id=store_id, name="أكواب"))
    session.add(
        AgentRun(
            research_run_id=run_id,
            agent_type="crawl_agent_run",
            status=RunStatus.completed,
            completed_at=datetime.now(timezone.utc),
            findings={"pages_crawled": 5},
        )
    )
    session.add(AgentRun(research_run_id=run_id, agent_type="ai_classification_agent_run", status=RunStatus.running))
    session.commit()
    session.close()

    body = client.get(f"/stores/{store_id}/understanding").json()

    assert body["understanding_stage"] == "partial"
    assert body["last_analyzed_at"] is not None
    assert body["products_found"] == 1
    assert body["categories_found"] == 1
    assert body["business_type"] is None  # classification not done yet — never guessed


def test_understanding_is_ready_with_real_fields_once_classification_completes(client, monkeypatch):
    store_id, run_id = _create_store(client, monkeypatch)
    session = _session()
    category = Category(store_id=store_id, name="أكواب")
    session.add(category)
    session.commit()
    session.refresh(category)
    session.add(Product(store_id=store_id, name="كوب قهوة", url="https://sonay.sa/p/1", category_id=category.id, price=45.0, currency="SAR"))
    session.add(Product(store_id=store_id, name="كوب سفر", url="https://sonay.sa/p/2", category_id=category.id))
    session.add(Brand(store_id=store_id, name="SONAY", aliases=["Sonay Coffee"]))
    session.add(
        AgentRun(
            research_run_id=run_id,
            agent_type="crawl_agent_run",
            status=RunStatus.completed,
            completed_at=datetime.now(timezone.utc),
        )
    )
    session.add(
        AgentRun(
            research_run_id=run_id,
            agent_type="ai_classification_agent_run",
            status=RunStatus.completed,
            findings={
                "business_type": "القهوة وأدوات تحضيرها",
                "primary_categories": ["قهوة مختصة", "أكواب"],
                "target_audience": ["عشاق القهوة"],
                "confidence": 0.87,
            },
        )
    )
    session.commit()
    session.close()

    body = client.get(f"/stores/{store_id}/understanding").json()

    assert body["understanding_stage"] == "ready"
    assert body["business_type"] == "القهوة وأدوات تحضيرها"
    assert body["primary_categories"] == ["قهوة مختصة", "أكواب"]
    assert body["target_audience"] == ["عشاق القهوة"]
    assert body["classification_confidence"] == pytest.approx(0.87)
    assert body["products_found"] == 2
    assert body["brands_found"] == 1
    assert len(body["top_categories"]) == 1
    assert body["top_categories"][0]["name"] == "أكواب"
    assert body["top_categories"][0]["product_count"] == 2
    assert len(body["product_samples"]) == 2
    assert body["product_samples"][0]["category_name"] == "أكواب"
    assert body["brand"]["name"] == "SONAY"
    assert body["brand"]["is_guessed"] is False
    assert body["display_name"] == "SONAY"


def test_understanding_is_low_confidence_when_classification_was_skipped(client, monkeypatch):
    """A crawl that completed but found too little to classify at all
    (skipped, per the observation-count gate) must never be shown as
    "ready" with a null business_type looking like a confirmed fact."""
    store_id, run_id = _create_store(client, monkeypatch)
    session = _session()
    session.add(
        AgentRun(
            research_run_id=run_id, agent_type="crawl_agent_run",
            status=RunStatus.completed, completed_at=datetime.now(timezone.utc),
        )
    )
    session.add(
        AgentRun(
            research_run_id=run_id, agent_type="ai_classification_agent_run",
            status=RunStatus.completed,
            findings={"skipped": True, "reason": "insufficient_observations", "observations_count": 1, "min_required": 3},
        )
    )
    session.commit()
    session.close()

    body = client.get(f"/stores/{store_id}/understanding").json()

    assert body["understanding_stage"] == "low_confidence"
    assert body["classification_skipped"] is True
    assert body["business_type"] is None


def test_understanding_is_low_confidence_when_below_confidence_threshold(client, monkeypatch):
    """A classification that did run but at low confidence must not be
    presented identically to a genuinely confident one."""
    store_id, run_id = _create_store(client, monkeypatch)
    session = _session()
    session.add(
        AgentRun(
            research_run_id=run_id, agent_type="crawl_agent_run",
            status=RunStatus.completed, completed_at=datetime.now(timezone.utc),
        )
    )
    session.add(
        AgentRun(
            research_run_id=run_id, agent_type="ai_classification_agent_run",
            status=RunStatus.completed,
            findings={"business_type": "غير واضح", "primary_categories": [], "target_audience": [], "confidence": 0.2},
        )
    )
    session.commit()
    session.close()

    body = client.get(f"/stores/{store_id}/understanding").json()

    assert body["understanding_stage"] == "low_confidence"
    assert body["classification_skipped"] is False
    assert body["classification_confidence"] == pytest.approx(0.2)


def test_understanding_marks_brand_as_guessed_but_still_surfaces_a_domain_derived_display_name(client, monkeypatch):
    """SIGNUP re-scope (brand-name fallback chain): a guessed Brand.name is
    still not treated as a *confirmed* fact (is_guessed stays True — the
    edit affordance and downstream alias-recording logic key off this) —
    but display_name must no longer be a bare None either. Blocking the
    whole /signup journey on 'we truly could not name your store' was the
    exact bug the fallback chain (structured data -> og:site_name -> title
    -> logo alt -> domain-derived name, the last of which never fails)
    exists to close: the user asked to start visibility analysis
    automatically once *any* usable name exists, even a domain-derived
    one, never blocking on a stronger source."""
    store_id, run_id = _create_store(client, monkeypatch, url="https://sonay.sa")
    session = _session()
    # Same shape _guess_brand_name_from_domain would produce for sonay.sa.
    session.add(Brand(store_id=store_id, name="Sonay"))
    session.add(AgentRun(research_run_id=run_id, agent_type="crawl_agent_run", status=RunStatus.completed))
    session.commit()
    session.close()

    body = client.get(f"/stores/{store_id}/understanding").json()

    assert body["brand"]["is_guessed"] is True
    # No PageObservation exists in this test either, so the fallback chain
    # itself lands on its own last resort (domain-derived), independent of
    # the guessed Brand row.
    assert body["display_name"] == "Sonay"


def test_understanding_is_failed_when_crawl_step_failed(client, monkeypatch):
    store_id, run_id = _create_store(client, monkeypatch)
    session = _session()
    session.add(AgentRun(research_run_id=run_id, agent_type="crawl_agent_run", status=RunStatus.failed, error="fetch timeout"))
    session.commit()
    session.close()

    body = client.get(f"/stores/{store_id}/understanding").json()

    assert body["understanding_stage"] == "failed"


def test_understanding_404_for_unknown_store(client):
    response = client.get(f"/stores/{uuid.uuid4()}/understanding")
    assert response.status_code == 404


def test_feedback_confirmed_is_persisted(client, monkeypatch):
    store_id, run_id = _create_store(client, monkeypatch)

    response = client.post(f"/stores/{store_id}/understanding/feedback", json={"feedback_type": "confirmed"})

    assert response.status_code == 200
    body = response.json()
    assert body["feedback_type"] == "confirmed"
    assert body["issues"] == []
    assert body["created_at"]


def test_feedback_incorrect_persists_issues_and_note(client, monkeypatch):
    store_id, run_id = _create_store(client, monkeypatch)

    response = client.post(
        f"/stores/{store_id}/understanding/feedback",
        json={"feedback_type": "incorrect", "issues": ["category_wrong", "products_wrong"], "note": "الفئات غير دقيقة"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["issues"] == ["category_wrong", "products_wrong"]
    assert body["note"] == "الفئات غير دقيقة"


def test_feedback_rejects_invalid_feedback_type(client, monkeypatch):
    store_id, run_id = _create_store(client, monkeypatch)

    response = client.post(f"/stores/{store_id}/understanding/feedback", json={"feedback_type": "maybe"})

    assert response.status_code == 422


def test_feedback_404_for_unknown_store(client):
    response = client.post(f"/stores/{uuid.uuid4()}/understanding/feedback", json={"feedback_type": "confirmed"})
    assert response.status_code == 404


def test_product_detail_returns_real_fields(client, monkeypatch):
    store_id, run_id = _create_store(client, monkeypatch)
    session = _session()
    category = Category(store_id=store_id, name="أكواب")
    session.add(category)
    session.commit()
    session.refresh(category)
    product = Product(store_id=store_id, name="كوب قهوة", url="https://sonay.sa/p/1", category_id=category.id, price=45.0, currency="SAR", availability="in_stock")
    session.add(product)
    session.commit()
    session.refresh(product)
    session.close()

    response = client.get(f"/stores/{store_id}/products/{product.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "كوب قهوة"
    assert body["category_name"] == "أكواب"
    assert body["price"] == pytest.approx(45.0)
    assert body["availability"] == "in_stock"


def test_product_detail_404_when_product_belongs_to_a_different_store(client, monkeypatch):
    store_id, _ = _create_store(client, monkeypatch, url="https://a.com")
    other_store_id, _ = _create_store(client, monkeypatch, url="https://b.com")
    session = _session()
    product = Product(store_id=other_store_id, name="X", url="https://b.com/p/1")
    session.add(product)
    session.commit()
    session.refresh(product)
    session.close()

    response = client.get(f"/stores/{store_id}/products/{product.id}")

    assert response.status_code == 404


def test_display_name_resolves_via_fallback_chain_when_web_search_failed_but_crawl_succeeded(client, monkeypatch):
    """The exact real bug this whole chain exists to fix: web_search
    identity resolution failed/was skipped, but the crawl+classification
    path succeeded confidently and the home page's own structured data
    names the store. display_name must resolve (never None), the stage
    must reach 'ready' (not stuck at needs_confirmation — see
    test_understanding_stage_v2.py for that layer), and none of this
    should require the AI-resolved identity to have worked at all."""
    store_id, run_id = _create_store(client, monkeypatch, url="https://modernsupply.com.sa")
    session = _session()
    session.add(AgentRun(research_run_id=run_id, agent_type="crawl_agent_run", status=RunStatus.completed))
    session.add(AgentRun(
        research_run_id=run_id, agent_type="ai_classification_agent_run", status=RunStatus.completed,
        findings={"business_type": "متجر إلكتروني", "primary_categories": ["بقالة"], "target_audience": [], "confidence": 0.85},
    ))
    session.add(AgentRun(
        research_run_id=run_id, agent_type="store_identity_agent_run", status=RunStatus.completed,
        findings={"reason": "web_search_unavailable_or_failed", "skipped": True},
    ))
    page = Page(store_id=store_id, url="https://modernsupply.com.sa/", page_type="home")
    session.add(page)
    session.commit()
    session.refresh(page)
    session.add(PageObservation(
        store_id=store_id, research_run_id=run_id, source_url=page.url, extractor_version="v2",
        normalized_extraction={"json_ld": [{"@type": "Organization", "name": "مودرن سبلاي"}]},
    ))
    session.commit()
    session.close()

    body = client.get(f"/stores/{store_id}/understanding").json()

    assert body["understanding_stage"] == "ready"
    assert body["display_name"] == "مودرن سبلاي"


def test_confirm_brand_name_persists_new_name_and_records_old_name_and_domain_as_aliases(client, monkeypatch):
    store_id, _run_id = _create_store(client, monkeypatch, url="https://flowery.sa")
    session = _session()
    session.add(Brand(store_id=store_id, name="Flowery"))
    session.commit()
    session.close()

    response = client.post(f"/stores/{store_id}/brand-name", json={"name": "فلاوري"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "فلاوري"
    assert "Flowery" in body["aliases"]
    assert "flowery.sa" in body["aliases"]

    # Persisted, not just echoed back.
    understanding = client.get(f"/stores/{store_id}/understanding").json()
    assert understanding["brand"]["name"] == "فلاوري"
    assert set(understanding["brand"]["aliases"]) >= {"Flowery", "flowery.sa"}


def test_confirm_brand_name_creates_a_brand_row_when_none_exists_yet(client, monkeypatch):
    store_id, _run_id = _create_store(client, monkeypatch, url="https://flowery.sa")

    response = client.post(f"/stores/{store_id}/brand-name", json={"name": "فلاوري"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "فلاوري"
    assert body["aliases"] == ["flowery.sa"]


def test_confirm_brand_name_rejects_empty_name(client, monkeypatch):
    store_id, _run_id = _create_store(client, monkeypatch, url="https://flowery.sa")
    response = client.post(f"/stores/{store_id}/brand-name", json={"name": "   "})
    assert response.status_code == 422


def test_confirm_brand_name_404_for_unknown_store(client):
    response = client.post(f"/stores/{uuid.uuid4()}/brand-name", json={"name": "اسم"})
    assert response.status_code == 404
