import json

from sqlmodel import select

from app.ai_visibility.prompt_family_engine import run_prompt_family_agent, select_top_intents
from app.models.ai_visibility import PromptFamily, PromptVariant
from app.models.intent import Intent, IntentSource
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute


class FakePromptFamilyProvider(AIProvider):
    name = "fake_prompt_family"

    async def generate(self, request: AIRequest) -> AIResponse:
        payload = json.dumps(
            {
                "prompts": [
                    "وش أفضل عطر رجالي للصيف؟",
                    "أبي عطر صيفي ثابت بأقل من 300 ريال",
                    "رشح لي عطر رجالي مناسب للدوام",
                ]
            }
        )
        return AIResponse(
            provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=15, output_tokens=15)
        )


def _make_store_with_intents(session, count: int = 2):
    org = Organization(name="t", slug="t-prompt-family")
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

    intents = []
    for i in range(count):
        intent = Intent(
            store_id=store.id,
            research_run_id=run.id,
            topic=f"topic-{i}",
            category="عطور",
            country="sa",
            language="ar",
            confidence=1.0 - i * 0.1,
            source=IntentSource.deterministic_catalog,
        )
        session.add(intent)
        session.commit()
        session.refresh(intent)
        intents.append(intent)

    return store, run, intents


def test_select_top_intents_orders_by_confidence_and_caps(session):
    store, run, intents = _make_store_with_intents(session, count=5)

    top = select_top_intents(session, run.id, max_intents=2)

    assert len(top) == 2
    assert top[0].confidence >= top[1].confidence


async def test_run_prompt_family_agent_persists_families_and_variants(session):
    store, run, intents = _make_store_with_intents(session, count=2)
    router = ModelRouter(
        providers={"fake": FakePromptFamilyProvider()},
        routes={"prompt_family_generation": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )

    variants = await run_prompt_family_agent(
        session=session,
        router=router,
        research_run_id=run.id,
        agent_run_id=None,
        intents=intents,
        max_prompts_per_intent=3,
    )

    assert len(variants) == 6  # 2 intents x 3 prompts each

    families = session.exec(select(PromptFamily).where(PromptFamily.research_run_id == run.id)).all()
    assert len(families) == 2

    persisted_variants = session.exec(select(PromptVariant)).all()
    assert len(persisted_variants) == 6
    assert "عطر رجالي" in persisted_variants[0].text


async def test_run_prompt_family_agent_respects_max_prompts_per_intent(session):
    store, run, intents = _make_store_with_intents(session, count=1)
    router = ModelRouter(
        providers={"fake": FakePromptFamilyProvider()},
        routes={"prompt_family_generation": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )

    variants = await run_prompt_family_agent(
        session=session,
        router=router,
        research_run_id=run.id,
        agent_run_id=None,
        intents=intents,
        max_prompts_per_intent=2,
    )

    assert len(variants) == 2  # provider offered 3, cap is 2
