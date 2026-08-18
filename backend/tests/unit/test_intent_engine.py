import json

from sqlmodel import select

from app.intent.intent_engine import generate_deterministic_seed_intents, run_intent_expansion_agent
from app.models.catalog import Category
from app.models.evidence import Evidence
from app.models.intent import IntentKeyword, IntentSource
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute


class FakeIntentExpanderProvider(AIProvider):
    name = "fake_intent"

    async def generate(self, request: AIRequest) -> AIResponse:
        payload = json.dumps(
            {
                "intents": [
                    {
                        "topic": "عطور رجالية صيفية",
                        "category": "عطور",
                        "commercial_stage": "consideration",
                        "estimated_demand": "high",
                        "keywords": ["عطر رجالي صيفي", "افضل عطر رجالي للصيف"],
                        "confidence": 0.85,
                    }
                ]
            }
        )
        return AIResponse(
            provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=20, output_tokens=20)
        )


def _make_store(session):
    org = Organization(name="t", slug="t-intent")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://example.com")
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    return store, run


def test_generate_deterministic_seed_intents_from_categories(session):
    store, run = _make_store(session)
    categories = [
        Category(store_id=store.id, name="عطور رجالية"),
        Category(store_id=store.id, name="عطور نسائية"),
    ]
    for c in categories:
        session.add(c)
    session.commit()
    for c in categories:
        session.refresh(c)

    intents = generate_deterministic_seed_intents(
        session,
        store_id=store.id,
        research_run_id=run.id,
        categories=categories,
        country="sa",
        language="ar",
        max_intents=10,
    )

    assert len(intents) == 2
    assert all(i.source == IntentSource.deterministic_catalog for i in intents)
    assert all(i.confidence == 1.0 for i in intents)

    links = session.exec(select(IntentKeyword)).all()
    assert len(links) == 2
    assert all(link.is_primary for link in links)


def test_generate_deterministic_seed_intents_respects_budget_and_dedup(session):
    store, run = _make_store(session)
    categories = [
        Category(store_id=store.id, name="عطور"),
        Category(store_id=store.id, name="عطور"),  # duplicate name, should dedup
        Category(store_id=store.id, name="ساعات"),
    ]
    for c in categories:
        session.add(c)
    session.commit()

    intents = generate_deterministic_seed_intents(
        session,
        store_id=store.id,
        research_run_id=run.id,
        categories=categories,
        country="sa",
        language="ar",
        max_intents=1,
    )
    assert len(intents) == 1  # budget cap of 1 wins even before dedup would kick in


async def test_intent_expansion_agent_persists_intents_keywords_and_evidence(session):
    store, run = _make_store(session)
    router = ModelRouter(
        providers={"fake": FakeIntentExpanderProvider()},
        routes={"intent_expansion": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )

    intents = await run_intent_expansion_agent(
        session=session,
        router=router,
        store_id=store.id,
        research_run_id=run.id,
        agent_run_id=None,
        categories=[],
        products=[],
        country="sa",
        language="ar",
        max_intents=10,
        already_generated=0,
    )

    assert len(intents) == 1
    assert intents[0].source == IntentSource.ai_expansion
    assert intents[0].commercial_stage.value == "consideration"
    assert intents[0].estimated_demand.value == "high"

    evidence = session.exec(select(Evidence).where(Evidence.store_id == store.id)).all()
    assert len(evidence) == 1

    links = session.exec(select(IntentKeyword).where(IntentKeyword.intent_id == intents[0].id)).all()
    assert len(links) == 2


async def test_intent_expansion_agent_uses_fallback_page_titles_when_catalog_empty(session):
    """Real bug reproduction: on stores where URL-pattern page classification
    tags nothing as product/category (seen on real Salla/Zid-style test
    stores), categories/products are empty and expansion used to get
    '(لا توجد بيانات كتالوج)' — zero intents. It should fall back to raw
    page titles instead."""
    store, run = _make_store(session)

    captured_requests = []

    class RecordingProvider(FakeIntentExpanderProvider):
        async def generate(self, request):
            captured_requests.append(request)
            return await super().generate(request)

    router = ModelRouter(
        providers={"fake": RecordingProvider()},
        routes={"intent_expansion": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )

    await run_intent_expansion_agent(
        session=session,
        router=router,
        store_id=store.id,
        research_run_id=run.id,
        agent_run_id=None,
        categories=[],
        products=[],
        fallback_page_titles=["أفضل قهوة مختصة", "أدوات تحضير القهوة"],
        country="sa",
        language="ar",
        max_intents=10,
        already_generated=0,
    )

    assert len(captured_requests) == 1
    user_message = captured_requests[0].messages[-1].content
    assert "أفضل قهوة مختصة" in user_message
    assert "(لا توجد بيانات كتالوج)" not in user_message


async def test_intent_expansion_agent_respects_remaining_budget(session):
    store, run = _make_store(session)
    router = ModelRouter(
        providers={"fake": FakeIntentExpanderProvider()},
        routes={"intent_expansion": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )

    intents = await run_intent_expansion_agent(
        session=session,
        router=router,
        store_id=store.id,
        research_run_id=run.id,
        agent_run_id=None,
        categories=[],
        products=[],
        country="sa",
        language="ar",
        max_intents=5,
        already_generated=5,
    )
    assert intents == []
