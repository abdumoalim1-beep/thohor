"""Phase 7 (scenario group: identity resolver) — resolve_store_identity
against a real ModelRouter backed by a fake AIProvider (same technique as
test_intent_engine.py's FakeIntentExpanderProvider), never a real network
call. Covers: successful resolution with sources persisted as Evidence,
a low-confidence-but-still-real result, an AI-provider failure, and a
timeout — all of which must degrade to (None, None), never raise, since
the orchestrator's premise is that identity resolution failing must never
block the rest of the run."""

import asyncio
import json

from sqlmodel import select

from app.models.evidence import Evidence, EvidenceSourceType
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.providers.ai.base import AIProvider, AIProviderError, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute
from app.store_intelligence.identity_resolver import resolve_store_identity


class FakeIdentityProvider(AIProvider):
    name = "fake_identity"

    def __init__(self, payload: dict | None = None, raise_error: bool = False, hang_seconds: float | None = None):
        self._payload = payload
        self._raise_error = raise_error
        self._hang_seconds = hang_seconds

    async def generate(self, request: AIRequest) -> AIResponse:
        if self._hang_seconds is not None:
            await asyncio.sleep(self._hang_seconds)
        if self._raise_error:
            raise AIProviderError("provider unavailable")
        return AIResponse(
            provider=self.name, model=request.model, text=json.dumps(self._payload),
            usage=AIUsage(input_tokens=10, output_tokens=10),
        )


def _make_store(session):
    org = Organization(name="t", slug="t-identity")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://flowery.example")
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
        routes={"store_identity_resolution": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )


_VALID_PAYLOAD = {
    "brand_name": "فلاوري", "business_type": "متجر ورد", "description": "وصف", "country": "SA", "city": "جدة",
    "language": "ar", "platform": "shopify", "categories": ["ورد"], "target_audiences": ["أفراد"],
    "market_signals": ["محلي"], "confidence": 0.9,
    "sources": [{"url": "https://example.com/a", "title": "A"}, {"url": "https://example.com/b", "title": "B"}],
}


async def test_successful_resolution_persists_aggregate_and_citation_evidence(session):
    store, run = _make_store(session)
    provider = FakeIdentityProvider(payload=_VALID_PAYLOAD)

    identity, evidence_id = await resolve_store_identity(
        session=session, router=_router(provider), store_id=store.id,
        research_run_id=run.id, agent_run_id=None, store_url=store.url,
    )

    assert identity is not None
    assert identity.brand_name == "فلاوري"
    assert identity.confidence == 0.9
    assert evidence_id is not None

    evidence = session.exec(select(Evidence).where(Evidence.store_id == store.id)).all()
    assert len(evidence) == 3  # 1 aggregate ai_execution + 2 web_search_citation
    aggregate = [e for e in evidence if e.source_type == EvidenceSourceType.ai_execution]
    citations = [e for e in evidence if e.source_type == EvidenceSourceType.web_search_citation]
    assert len(aggregate) == 1
    assert len(citations) == 2


async def test_low_confidence_result_returned_as_is(session):
    """A low-but-real confidence score is not a failure — the orchestrator/
    stage machine decides what to do with it (needs_confirmation), this
    function's job is just to report it honestly."""
    store, run = _make_store(session)
    payload = {**_VALID_PAYLOAD, "confidence": 0.1, "sources": [{"url": "https://example.com/a", "title": "A"}]}
    provider = FakeIdentityProvider(payload=payload)

    identity, evidence_id = await resolve_store_identity(
        session=session, router=_router(provider), store_id=store.id,
        research_run_id=run.id, agent_run_id=None, store_url=store.url,
    )

    assert identity is not None
    assert identity.confidence == 0.1
    assert evidence_id is not None


async def test_provider_failure_degrades_to_none_never_raises(session):
    store, run = _make_store(session)
    provider = FakeIdentityProvider(raise_error=True)

    identity, evidence_id = await resolve_store_identity(
        session=session, router=_router(provider), store_id=store.id,
        research_run_id=run.id, agent_run_id=None, store_url=store.url,
    )

    assert identity is None
    assert evidence_id is None
    assert session.exec(select(Evidence).where(Evidence.store_id == store.id)).all() == []


async def test_timeout_degrades_to_none_never_raises(session):
    store, run = _make_store(session)
    provider = FakeIdentityProvider(payload=_VALID_PAYLOAD, hang_seconds=1.0)

    identity, evidence_id = await resolve_store_identity(
        session=session, router=_router(provider), store_id=store.id,
        research_run_id=run.id, agent_run_id=None, store_url=store.url,
        timeout_seconds=0.05,
    )

    assert identity is None
    assert evidence_id is None
