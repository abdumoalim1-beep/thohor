"""Phase 7 (scenario group: identity-based competitor discovery) —
discover_competitors against a fake AIProvider. Covers: real domains get
persisted with auto-confirm applied by the same rule the module documents,
duplicate domains across two calls get merged (not duplicated) via
get_or_create_competitor's existing dedup, and known non-competitor
categories (marketplace/social/...) are excluded by reusing
classify_known_domain — never a second, divergent exclusion list."""

import json

from sqlmodel import select

from app.competitors.identity_discovery import discover_competitors
from app.models.competitor import Competitor, CompetitorType
from app.models.evidence import Evidence
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute
from app.schemas.store_identity import StoreIdentity


class FakeCompetitorDiscoveryProvider(AIProvider):
    name = "fake_discovery"

    def __init__(self, competitors: list[dict]):
        self._competitors = competitors

    async def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            provider=self.name, model=request.model,
            text=json.dumps({"competitors": self._competitors}),
            usage=AIUsage(input_tokens=10, output_tokens=10),
        )


def _make_store(session, url="https://flowery.example"):
    org = Organization(name="t", slug=f"t-discovery-{url}")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url=url)
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    return store, run


def _router(provider: AIProvider) -> ModelRouter:
    return ModelRouter(
        providers={"fake": provider},
        routes={"competitor_discovery_search": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )


_IDENTITY = StoreIdentity(brand_name="فلاوري", business_type="متجر ورد", categories=["ورد"], confidence=0.9)


async def test_real_competitors_persisted_with_evidence_and_auto_confirm(session):
    store, run = _make_store(session)
    competitors = [
        {
            "name": "بلوم باكيت", "domain": "bloom-bucket.com", "description": "منافس حقيقي",
            "categories": ["ورد"], "market": "محلي", "confidence": 0.9,
            "sources": [{"url": "https://a.example/x", "title": "A"}, {"url": "https://b.example/y", "title": "B"}],
        },
    ]
    provider = FakeCompetitorDiscoveryProvider(competitors)

    persisted, evidence_ids = await discover_competitors(
        session=session, router=_router(provider), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, store_url=store.url, identity=_IDENTITY,
    )

    assert len(persisted) == 1
    assert persisted[0].domain == "bloom-bucket.com"
    assert persisted[0].competitor_type == CompetitorType.identity_web_search
    # 2 sources clears the auto-confirm bar (>=2 independent sources).
    assert persisted[0].confirmation_status == "auto_confirmed"
    assert persisted[0].classification == "direct_competitor"

    evidence = session.exec(select(Evidence).where(Evidence.store_id == store.id)).all()
    assert len(evidence) == 3  # 1 aggregate + 2 citations


async def test_single_low_confidence_source_stays_pending_confirmation(session):
    store, run = _make_store(session)
    competitors = [
        {
            "name": "متجر مشكوك فيه", "domain": "maybe-competitor.com", "confidence": 0.3,
            "sources": [{"url": "https://only.example/x", "title": "X"}],
        },
    ]
    provider = FakeCompetitorDiscoveryProvider(competitors)

    persisted, _ = await discover_competitors(
        session=session, router=_router(provider), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, store_url=store.url, identity=_IDENTITY,
    )

    assert len(persisted) == 1
    assert persisted[0].confirmation_status == "pending_user_confirmation"
    assert persisted[0].classification == "unknown"


async def test_known_marketplace_domain_is_excluded_never_persisted(session):
    store, run = _make_store(session)
    competitors = [
        {"name": "Amazon", "domain": "amazon.sa", "confidence": 0.9, "sources": [{"url": "https://amazon.sa", "title": "Amazon"}]},
        {
            "name": "منافس حقيقي", "domain": "real-competitor.com", "confidence": 0.8,
            "sources": [{"url": "https://x.example", "title": "X"}],
        },
    ]
    provider = FakeCompetitorDiscoveryProvider(competitors)

    persisted, _ = await discover_competitors(
        session=session, router=_router(provider), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, store_url=store.url, identity=_IDENTITY,
    )

    domains = {c.domain for c in persisted}
    assert "amazon.sa" not in domains
    assert "real-competitor.com" in domains


async def test_own_store_domain_never_persisted_as_its_own_competitor(session):
    store, run = _make_store(session, url="https://myflowershop.com")
    competitors = [
        {"name": "نفسي", "domain": "myflowershop.com", "confidence": 0.9, "sources": [{"url": "https://x", "title": "X"}]},
    ]
    provider = FakeCompetitorDiscoveryProvider(competitors)

    persisted, _ = await discover_competitors(
        session=session, router=_router(provider), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, store_url=store.url, identity=_IDENTITY,
    )

    assert persisted == []


async def test_same_domain_across_two_calls_is_merged_not_duplicated(session):
    store, run = _make_store(session)
    competitors = [
        {"name": "بلوم باكيت", "domain": "bloom-bucket.com", "confidence": 0.9, "sources": [{"url": "https://x", "title": "X"}]},
    ]
    provider = FakeCompetitorDiscoveryProvider(competitors)
    router = _router(provider)

    await discover_competitors(
        session=session, router=router, store_id=store.id, research_run_id=run.id,
        agent_run_id=None, store_url=store.url, identity=_IDENTITY,
    )
    await discover_competitors(
        session=session, router=router, store_id=store.id, research_run_id=run.id,
        agent_run_id=None, store_url=store.url, identity=_IDENTITY,
    )

    rows = session.exec(select(Competitor).where(Competitor.store_id == store.id, Competitor.domain == "bloom-bucket.com")).all()
    assert len(rows) == 1


async def test_max_suggestions_caps_how_many_are_persisted(session):
    store, run = _make_store(session)
    competitors = [
        {"name": f"منافس {i}", "domain": f"competitor-{i}.com", "confidence": 0.9, "sources": [{"url": f"https://{i}.example", "title": "X"}]}
        for i in range(5)
    ]
    provider = FakeCompetitorDiscoveryProvider(competitors)

    persisted, _ = await discover_competitors(
        session=session, router=_router(provider), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, store_url=store.url, identity=_IDENTITY, max_suggestions=2,
    )

    assert len(persisted) == 2
