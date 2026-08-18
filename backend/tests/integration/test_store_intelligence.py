"""Integration tests — real network (crawls a real public site), fake
storage/AI provider to avoid needing MinIO or a paid API key. Not part of
the default `pytest` run; execute explicitly with `pytest tests/integration`.
"""

from sqlmodel import select

from app.crawler.extract import EXTRACTOR_VERSION
from app.crawler.store_intelligence import run_crawl_agent, run_store_classification_agent
from app.models.catalog import Page
from app.models.evidence import Evidence
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute

TEST_STORE_URL = "https://books.toscrape.com"


class FakeStorage:
    def put_text(self, key_prefix: str, content: str, content_type: str = "text/html") -> str:
        return f"fake://{key_prefix}"


class FakeClassifierProvider(AIProvider):
    """Returns a fixed, schema-valid StoreClassification payload — stands in
    for a real model so this test doesn't need an API key."""

    name = "fake_classifier"

    async def generate(self, request: AIRequest) -> AIResponse:
        import json

        payload = json.dumps(
            {
                "business_type": "bookstore",
                "primary_categories": ["books"],
                "target_audience": ["readers"],
                "inferred_attributes": ["online catalog"],
                "confidence": 0.8,
            }
        )
        return AIResponse(
            provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=10, output_tokens=10)
        )


async def _make_store(session) -> Store:
    org = Organization(name="Test Org", slug="test-org")
    session.add(org)
    session.commit()
    session.refresh(org)

    store = Store(organization_id=org.id, url=TEST_STORE_URL)
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


async def test_baseline_crawl_persists_pages_and_observations(session):
    store = await _make_store(session)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)

    observations = await run_crawl_agent(
        session=session,
        storage=FakeStorage(),
        store_id=store.id,
        research_run_id=run.id,
        agent_run_id=None,
        base_url=store.url,
        max_pages=6,
        max_depth=2,
        request_timeout_seconds=10,
        max_response_bytes=5_000_000,
        user_agent="MersadBot/0.1 (+https://mersad.example/bot)",
    )

    assert len(observations) > 0
    assert all(obs.extractor_version == EXTRACTOR_VERSION for obs in observations)

    pages = session.exec(select(Page).where(Page.store_id == store.id)).all()
    assert len(pages) == len(observations)


async def test_classification_agent_creates_evidence_linked_to_ai_execution(session):
    store = await _make_store(session)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)

    observations = await run_crawl_agent(
        session=session,
        storage=FakeStorage(),
        store_id=store.id,
        research_run_id=run.id,
        agent_run_id=None,
        base_url=store.url,
        max_pages=4,
        max_depth=1,
        request_timeout_seconds=10,
        max_response_bytes=5_000_000,
        user_agent="MersadBot/0.1 (+https://mersad.example/bot)",
    )

    router = ModelRouter(
        providers={"fake": FakeClassifierProvider()},
        routes={"classification": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )

    classification, evidence_id = await run_store_classification_agent(
        session=session,
        router=router,
        store_id=store.id,
        research_run_id=run.id,
        agent_run_id=None,
        observations=observations,
    )

    assert classification is not None
    assert classification.business_type == "bookstore"
    assert evidence_id is not None

    evidence = session.get(Evidence, evidence_id)
    assert evidence is not None
    assert evidence.store_id == store.id
    assert evidence.confidence == 0.8
