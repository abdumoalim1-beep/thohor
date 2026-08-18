"""API layer test — sqlite in-memory DB via dependency override, Celery
`.delay()` monkeypatched to a no-op so this needs neither Postgres nor
Redis. It verifies routing + request/response wiring, not the crawl itself
(that's covered by tests/integration/test_store_intelligence.py).
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
import app.models  # noqa: F401 — registers all tables
from app.core.db import get_session
from app.crawler.extract import PageFacts
from app.crawler.subprocess_fetch import FetchedPage
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelRouter


class WinningPageProvider(AIProvider):
    name = "openai"

    async def generate(self, request: AIRequest) -> AIResponse:
        output = {
            "summary": "الصفحة تغطي الموضوع بصورة أوضح",
            "why_this_page_wins": ["عنوان واضح مرتبط بالموضوع"],
            "gaps": ["العنوان غير متوفر في صفحة المتجر"],
            "changes": [{
                "area": "H1", "competitor_observation": "Coffee guide", "store_observation": None,
                "recommended_change": "أنشئ H1 واضحًا", "evidence_basis": "H1 مرصود في الصفحة المتصدرة",
            }],
            "content_sections": ["الأنواع"],
            "assumptions_requiring_confirmation": [],
        }
        return AIResponse(provider=self.name, model=request.model, text=json.dumps(output), usage=AIUsage(input_tokens=20, output_tokens=30))


@pytest.fixture()
def client():
    # StaticPool: a plain "sqlite://" engine opens a fresh (empty) in-memory
    # DB per connection, so different requests wouldn't see each other's
    # tables/rows. StaticPool pins it to a single shared connection.
    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(test_engine)

    def override_get_session():
        with Session(test_engine) as session:
            yield session

    main_module.app.dependency_overrides[get_session] = override_get_session
    yield TestClient(main_module.app)
    main_module.app.dependency_overrides.clear()


def test_create_store_dispatches_run_and_returns_pending_status(client, monkeypatch):
    dispatched = {}
    monkeypatch.setattr(
        "app.api.stores.execute_research_run_task.delay",
        lambda store_id, run_id: dispatched.update(store_id=store_id, run_id=run_id),
    )

    response = client.post("/stores", json={"url": "https://example.com"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert dispatched["store_id"] == body["store_id"]
    assert dispatched["run_id"] == body["research_run_id"]


def test_get_store_returns_zeroed_counts_before_any_crawl(client, monkeypatch):
    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)

    create_response = client.post("/stores", json={"url": "https://example.com"})
    store_id = create_response.json()["store_id"]

    detail_response = client.get(f"/stores/{store_id}")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["url"] == "https://example.com"
    assert detail["pages_crawled"] == 0
    assert detail["latest_run"]["status"] == "pending"


def test_market_exploration_only_runs_after_explicit_post(client, monkeypatch):
    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    monkeypatch.setattr("app.api.stores.execute_market_exploration_task.delay", lambda *a, **k: None)
    created = client.post("/stores", json={"url": "https://example.com", "country": "sa", "language": "ar"}).json()

    estimate = client.get(f"/stores/{created['store_id']}/market-explorations/estimate")
    assert estimate.status_code == 200
    assert estimate.json()["max_queries"] == 3

    response = client.post(
        f"/stores/{created['store_id']}/market-explorations",
        json={"topic": "غرف أطفال", "max_queries": 3},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["kind"] == "market_exploration"
    status_response = client.get(f"/stores/{created['store_id']}/on-demand-analyses/{body['research_run_id']}/status")
    assert status_response.json()["status"] == "pending"


def test_failed_on_demand_job_can_be_retried_without_losing_request(client, monkeypatch):
    import uuid
    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    monkeypatch.setattr("app.api.stores.execute_market_exploration_task.delay", lambda *a, **k: None)
    created = client.post("/stores", json={"url": "https://example.com"}).json()
    job = client.post(
        f"/stores/{created['store_id']}/market-explorations", json={"topic": "coffee", "max_queries": 1}
    ).json()

    session_gen = main_module.app.dependency_overrides[get_session]()
    session = next(session_gen)
    from app.models.research import AgentRun, ResearchRun, RunStatus
    from sqlmodel import select

    run = session.get(ResearchRun, uuid.UUID(job["research_run_id"]))
    agent = session.exec(select(AgentRun).where(AgentRun.research_run_id == run.id)).first()
    run.status = RunStatus.failed; run.error = "temporary failure"
    agent.status = RunStatus.failed; agent.error = "temporary failure"
    session.add(run); session.add(agent); session.commit()

    retried = client.post(f"/stores/{created['store_id']}/on-demand-analyses/{job['research_run_id']}/retry")
    assert retried.status_code == 202
    assert retried.json()["status"] == "pending"
    session.refresh(agent)
    assert agent.findings["request"]["topic"] == "coffee"
    session_gen.close()


def test_winning_page_analysis_requires_observed_url_and_runs_on_selection(client, monkeypatch):
    from app.providers.search.mock_provider import MockSearchProvider

    session_gen = main_module.app.dependency_overrides[get_session]()
    test_session = next(session_gen)
    monkeypatch.setattr("app.workers.tasks.engine", test_session.get_bind())

    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    monkeypatch.setattr("app.workers.tasks.get_search_provider", lambda session: MockSearchProvider())
    monkeypatch.setattr("app.workers.tasks.get_router", lambda: ModelRouter(providers={"openai": WinningPageProvider()}))
    monkeypatch.setattr("app.api.stores.execute_market_exploration_task.delay", lambda store_id, run_id: __import__("app.workers.tasks", fromlist=["execute_market_exploration_task"]).execute_market_exploration_task.run(store_id, run_id))
    monkeypatch.setattr("app.api.stores.execute_winning_page_analysis_task.delay", lambda store_id, run_id: __import__("app.workers.tasks", fromlist=["execute_winning_page_analysis_task"]).execute_winning_page_analysis_task.run(store_id, run_id))

    async def fake_fetch(url, *_args, **_kwargs):
        facts = PageFacts(url=url, title="Coffee", h1="Coffee guide", body_text="Useful coffee guide")
        return FetchedPage(url=url, status_code=200, content_type="text/html", html="<h1>Coffee guide</h1>", facts=facts)

    monkeypatch.setattr("app.services.on_demand_jobs.fetch_and_extract_in_subprocess", fake_fetch)
    created = client.post("/stores", json={"url": "https://shop.test", "country": "sa", "language": "en"}).json()
    exploration = client.post(
        f"/stores/{created['store_id']}/market-explorations", json={"topic": "coffee", "max_queries": 1}
    ).json()
    exploration = client.get(f"/stores/{created['store_id']}/market-explorations/{exploration['research_run_id']}").json()
    selected = exploration["results"][0]

    response = client.post(f"/stores/{created['store_id']}/winning-page-analyses", json={
        "market_research_run_id": exploration["research_run_id"], "query": "coffee",
        "competitor_url": selected["url"],
    })
    assert response.status_code == 202
    analysis_run_id = response.json()["research_run_id"]
    completed_analysis = client.get(f"/stores/{created['store_id']}/winning-page-analyses/{analysis_run_id}")
    assert completed_analysis.json()["output"]["changes"][0]["area"] == "H1"

    converted = client.post(
        f"/stores/{created['store_id']}/winning-page-analyses/{analysis_run_id}/convert"
    )
    assert converted.status_code == 200
    assert converted.json()["recommendation_title"] == "أنشئ صفحة مخصصة لـ 'coffee'"

    converted_again = client.post(
        f"/stores/{created['store_id']}/winning-page-analyses/{analysis_run_id}/convert"
    )
    assert converted_again.status_code == 200
    assert converted_again.json()["opportunity_id"] == converted.json()["opportunity_id"]
    assert converted_again.json()["recommendation_id"] == converted.json()["recommendation_id"]

    history = client.get(f"/stores/{created['store_id']}/on-demand-analyses")
    assert history.status_code == 200
    assert [item["kind"] for item in history.json()["analyses"]] == [
        "winning_page_analysis", "market_exploration",
    ]
    assert history.json()["analyses"][0]["recommendation_id"] == converted.json()["recommendation_id"]

    restored_market = client.get(
        f"/stores/{created['store_id']}/market-explorations/{exploration['research_run_id']}"
    )
    assert restored_market.status_code == 200
    assert restored_market.json()["results"] == exploration["results"]

    restored_analysis = client.get(
        f"/stores/{created['store_id']}/winning-page-analyses/{analysis_run_id}"
    )
    assert restored_analysis.status_code == 200
    assert restored_analysis.json()["output"]["summary"] == "الصفحة تغطي الموضوع بصورة أوضح"

    rejected = client.post(f"/stores/{created['store_id']}/winning-page-analyses", json={
        "market_research_run_id": exploration["research_run_id"], "query": "coffee",
        "competitor_url": "https://not-observed.test/page",
    })
    assert rejected.status_code == 409
    session_gen.close()


@pytest.mark.parametrize("terminal_status", ["completed", "failed", "cancelled"])
def test_get_store_returns_progress_payload_for_terminal_runs(client, monkeypatch, terminal_status):
    """The polling contract exposes terminal status and each stage result."""
    import uuid
    from datetime import datetime, timezone

    from app.models.research import AgentRun, ResearchRun, RunStatus

    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    created = client.post("/stores", json={"url": "https://example.com"}).json()

    override = main_module.app.dependency_overrides[get_session]
    session_gen = override()
    session = next(session_gen)
    now = datetime.now(timezone.utc)
    run = session.get(ResearchRun, uuid.UUID(created["research_run_id"]))
    run.status = RunStatus(terminal_status)
    run.started_at = now
    run.completed_at = now
    run.error = "crawl_agent_run failed: upstream unavailable" if terminal_status == "failed" else None
    session.add(run)
    session.add(
        AgentRun(
            research_run_id=run.id,
            agent_type="crawl_agent_run",
            status=RunStatus.completed,
            started_at=now,
            completed_at=now,
            findings={"pages_crawled": 7},
        )
    )
    session.commit()
    session.close()

    response = client.get(f"/stores/{created['store_id']}")

    assert response.status_code == 200
    latest = response.json()["latest_run"]
    assert latest["id"] == created["research_run_id"]
    assert latest["status"] == terminal_status
    assert latest["created_at"]
    assert latest["started_at"]
    assert latest["completed_at"]
    assert latest["error"] == ("crawl_agent_run failed: upstream unavailable" if terminal_status == "failed" else None)
    assert len(latest["agent_runs"]) == 1
    agent = latest["agent_runs"][0]
    assert agent["agent_type"] == "crawl_agent_run"
    assert agent["status"] == "completed"
    assert agent["started_at"]
    assert agent["completed_at"]
    assert agent["findings"] == {"pages_crawled": 7}
    assert agent["error"] is None


def test_get_store_exposes_real_store_profile_before_run_completion(client, monkeypatch):
    """Store identity/catalog facts are available while later stages run."""
    import uuid
    from datetime import datetime, timezone

    from app.models.catalog import Brand, Category, Page, Product
    from app.models.observation import PageObservation
    from app.models.research import AgentRun, ResearchRun, RunStatus

    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    created = client.post("/stores", json={"url": "https://sonay.sa"}).json()
    override = main_module.app.dependency_overrides[get_session]
    session_gen = override()
    session = next(session_gen)
    store_id = uuid.UUID(created["store_id"])
    run_id = uuid.UUID(created["research_run_id"])
    run = session.get(ResearchRun, run_id)
    run.status = RunStatus.running
    run.started_at = datetime.now(timezone.utc)
    home = Page(store_id=store_id, url="https://sonay.sa/", page_type="home")
    product_page = Page(store_id=store_id, url="https://sonay.sa/products/cup", page_type="product")
    session.add(home)
    session.add(product_page)
    session.commit()
    session.refresh(home)
    session.refresh(product_page)
    session.add(Product(store_id=store_id, name="كوب قهوة", url=product_page.url))
    session.add(Category(store_id=store_id, name="أكواب", url="https://sonay.sa/collections/cups"))
    session.add(Brand(store_id=store_id, name="SONAY"))
    session.add(
        PageObservation(
            store_id=store_id,
            research_run_id=run_id,
            page_id=home.id,
            source_url=home.url,
            extractor_version="v1",
            normalized_extraction={
                "title": "SONAY | القهوة المختصة",
                "meta_description": "قهوة وأدوات تحضير.",
                "json_ld": [{"@type": "Organization", "name": "SONAY"}],
            },
        )
    )
    session.add(
        PageObservation(
            store_id=store_id,
            research_run_id=run_id,
            page_id=product_page.id,
            source_url=product_page.url,
            extractor_version="v1",
            normalized_extraction={
                "json_ld": [
                    {"@type": "Product", "name": "كوب قهوة", "image": "https://cdn.sonay.sa/cup.jpg"}
                ]
            },
        )
    )
    session.add(
        AgentRun(
            research_run_id=run_id,
            agent_type="crawl_agent_run",
            status=RunStatus.completed,
            findings={"pages_crawled": 2},
        )
    )
    session.add(
        AgentRun(
            research_run_id=run_id,
            agent_type="ai_classification_agent_run",
            status=RunStatus.completed,
            findings={
                "business_type": "القهوة وأدوات تحضير القهوة",
                "primary_categories": ["قهوة مختصة", "أكواب"],
                "confidence": 0.91,
            },
        )
    )
    session.commit()
    session.close()

    detail = client.get(f"/stores/{created['store_id']}").json()

    assert detail["latest_run"]["status"] == "running"
    profile = detail["store_profile"]
    assert profile["name"] == "SONAY"
    assert profile["domain"] == "sonay.sa"
    assert profile["business_type"] == "القهوة وأدوات تحضير القهوة"
    assert profile["primary_categories"] == ["قهوة مختصة", "أكواب"]
    assert profile["products_count"] == 1
    assert profile["categories_count"] == 1
    assert profile["pages_count"] == 2
    assert profile["products"][0]["image_url"] == "https://cdn.sonay.sa/cup.jpg"


def test_list_intent_clusters_empty_before_any_run_completes(client, monkeypatch):
    """Part Q1."""
    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    create_response = client.post("/stores", json={"url": "https://example.com"})
    store_id = create_response.json()["store_id"]

    response = client.get(f"/stores/{store_id}/intent-clusters")

    assert response.status_code == 200
    assert response.json() == {"clusters": []}


def test_list_intent_clusters_404_for_unknown_store(client):
    response = client.get("/stores/00000000-0000-0000-0000-000000000000/intent-clusters")
    assert response.status_code == 404


def test_get_store_404_for_unknown_id(client):
    response = client.get("/stores/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_trigger_research_run_404_for_unknown_store(client):
    response = client.post("/stores/00000000-0000-0000-0000-000000000000/research-runs")
    assert response.status_code == 404


def test_trigger_research_run_rejects_when_run_already_in_progress(client, monkeypatch):
    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    create_response = client.post("/stores", json={"url": "https://example.com"})
    store_id = create_response.json()["store_id"]

    # The just-created run is still "pending" (never actually executed in this test).
    response = client.post(f"/stores/{store_id}/research-runs")
    assert response.status_code == 409


def test_trigger_research_run_dispatches_monitoring_run_when_completed_run_exists(client, monkeypatch):
    dispatched = []
    monkeypatch.setattr(
        "app.api.stores.execute_research_run_task.delay",
        lambda store_id, run_id: dispatched.append((store_id, run_id)),
    )
    create_response = client.post("/stores", json={"url": "https://example.com"})
    store_id = create_response.json()["store_id"]
    first_run_id = create_response.json()["research_run_id"]

    # Simulate the first run having completed, so the store is eligible for a new one.
    import uuid

    import app.main as main_module
    from app.core.db import get_session as real_get_session
    from app.models.research import ResearchRun, RunStatus

    override = main_module.app.dependency_overrides[real_get_session]
    session_gen = override()
    session = next(session_gen)
    run = session.get(ResearchRun, uuid.UUID(first_run_id))
    run.status = RunStatus.completed
    session.add(run)
    session.commit()

    response = client.post(f"/stores/{store_id}/research-runs")
    assert response.status_code == 200
    body = response.json()
    assert body["research_run_id"] != first_run_id
    # dispatched[0] is from the initial POST /stores; dispatched[1] is this trigger.
    assert len(dispatched) == 2
    assert dispatched[1] == (store_id, body["research_run_id"])


def test_cancel_research_run_accepts_a_pending_run(client, monkeypatch):
    """Part H8."""
    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    create_response = client.post("/stores", json={"url": "https://example.com"})
    store_id = create_response.json()["store_id"]
    run_id = create_response.json()["research_run_id"]

    response = client.post(f"/stores/{store_id}/research-runs/{run_id}/cancel")

    assert response.status_code == 200
    body = response.json()
    assert body["research_run_id"] == run_id
    assert body["cancellation_requested"] is True


def test_cancel_research_run_is_idempotent(client, monkeypatch):
    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    create_response = client.post("/stores", json={"url": "https://example.com"})
    store_id = create_response.json()["store_id"]
    run_id = create_response.json()["research_run_id"]

    first = client.post(f"/stores/{store_id}/research-runs/{run_id}/cancel")
    second = client.post(f"/stores/{store_id}/research-runs/{run_id}/cancel")

    assert first.json()["cancellation_requested"] is True
    assert second.json()["cancellation_requested"] is False


def test_cancel_research_run_404_for_unknown_run(client):
    response = client.post(
        "/stores/00000000-0000-0000-0000-000000000000/research-runs/00000000-0000-0000-0000-000000000000/cancel"
    )
    assert response.status_code == 404


def test_cancel_research_run_404_when_run_belongs_to_a_different_store(client, monkeypatch):
    monkeypatch.setattr("app.api.stores.execute_research_run_task.delay", lambda *a, **k: None)
    first_store = client.post("/stores", json={"url": "https://example.com"}).json()
    second_store = client.post("/stores", json={"url": "https://example2.com"}).json()

    response = client.post(
        f"/stores/{second_store['store_id']}/research-runs/{first_store['research_run_id']}/cancel"
    )

    assert response.status_code == 404
