import json

from sqlmodel import select

from app.models.finding import Finding, FindingStatus
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.research_task import ResearchTask
from app.models.store import Store
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute
from app.research.budget import ResearchBudget
from app.research.capabilities import ResearchCapabilities
from app.research.planner import plan_next_tasks


class FakePlannerProvider(AIProvider):
    name = "fake_planner"

    async def generate(self, request: AIRequest) -> AIResponse:
        payload = json.dumps(
            {
                "new_tasks": [
                    {
                        "task_type": "competitor_deep_dive",
                        "target": "rival.test",
                        "reason": "يهيمن على عدة نوايا بترتيب قوي",
                        "hypothesis": "صفحة تصنيف مخصصة",
                        "priority": 0.85,
                    }
                ]
            }
        )
        return AIResponse(
            provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=30, output_tokens=20)
        )


class FakeMisbehavingPlannerProvider(AIProvider):
    """Ignores the prompt's 'don't propose unavailable task types'
    instruction — used to prove the deterministic filter in plan_next_tasks
    catches it regardless of what the model does (Part G-B4)."""

    name = "fake_misbehaving_planner"

    async def generate(self, request: AIRequest) -> AIResponse:
        payload = json.dumps(
            {
                "new_tasks": [
                    {
                        "task_type": "ai_visibility_gemini",
                        "target": "id=some-intent",
                        "reason": "تحقق من الظهور على Gemini",
                        "hypothesis": None,
                        "priority": 0.7,
                    },
                    {
                        "task_type": "competitor_deep_dive",
                        "target": "rival.test",
                        "reason": "يهيمن على عدة نوايا بترتيب قوي",
                        "hypothesis": None,
                        "priority": 0.85,
                    },
                ]
            }
        )
        return AIResponse(
            provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=30, output_tokens=20)
        )


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-planner")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    return store, run


def _all_capabilities() -> ResearchCapabilities:
    return ResearchCapabilities(configured_ai_surfaces=frozenset({"chatgpt", "gemini", "claude"}), search_configured=True)


def _budget() -> ResearchBudget:
    return ResearchBudget(
        max_search_requests=10,
        max_ai_requests=10,
        max_pages=10,
        max_tokens=10_000,
        max_cost_usd=1.0,
        max_duration_seconds=60.0,
        max_depth=3,
        max_tasks=10,
    )


async def test_plan_next_tasks_returns_suggestions_without_writing_to_db(session):
    store, run = _make_store_and_run(session)
    router = ModelRouter(
        providers={"fake": FakePlannerProvider()},
        routes={"research_planning": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )

    tasks_before = session.exec(select(ResearchTask)).all()
    findings_before = session.exec(select(Finding)).all()

    suggestions = await plan_next_tasks(
        session=session,
        router=router,
        research_run_id=run.id,
        agent_run_id=None,
        store_id=store.id,
        budget=_budget(),
        capabilities=_all_capabilities(),
    )

    assert len(suggestions) == 1
    assert suggestions[0].task_type.value == "competitor_deep_dive"
    assert suggestions[0].target == "rival.test"
    assert suggestions[0].priority == 0.85

    # Planner only suggests — never writes research_tasks/findings itself.
    tasks_after = session.exec(select(ResearchTask)).all()
    findings_after = session.exec(select(Finding)).all()
    assert len(tasks_after) == len(tasks_before)
    assert len(findings_after) == len(findings_before)


async def test_plan_next_tasks_handles_empty_state_gracefully(session):
    store, run = _make_store_and_run(session)
    router = ModelRouter(
        providers={"fake": FakePlannerProvider()},
        routes={"research_planning": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )

    # No competitors, findings, or prior tasks exist yet — digest building
    # must not error on empty query results.
    suggestions = await plan_next_tasks(
        session=session,
        router=router,
        research_run_id=run.id,
        agent_run_id=None,
        store_id=store.id,
        budget=_budget(),
        capabilities=_all_capabilities(),
    )

    assert len(suggestions) == 1


async def test_plan_next_tasks_includes_existing_findings_in_digest(session, monkeypatch):
    store, run = _make_store_and_run(session)
    session.add(
        Finding(
            store_id=store.id,
            research_run_id=run.id,
            finding_type="dominant_competitor",
            statement="rival.test يهيمن على مجموعة أدوات القهوة",
            confidence=0.6,
            status=FindingStatus.candidate,
        )
    )
    session.commit()

    captured_messages = {}

    class CapturingProvider(FakePlannerProvider):
        async def generate(self, request: AIRequest) -> AIResponse:
            captured_messages["messages"] = request.messages
            return await super().generate(request)

    router = ModelRouter(
        providers={"fake": CapturingProvider()},
        routes={"research_planning": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )

    await plan_next_tasks(
        session=session,
        router=router,
        research_run_id=run.id,
        agent_run_id=None,
        store_id=store.id,
        budget=_budget(),
        capabilities=_all_capabilities(),
    )

    user_message = next(m for m in captured_messages["messages"] if m.role.value == "user")
    assert "rival.test يهيمن على مجموعة أدوات القهوة" in user_message.content


async def test_plan_next_tasks_filters_suggestions_for_unconfigured_surfaces(session):
    """Part G-B4: even if the model ignores the prompt's instruction and
    proposes ai_visibility_gemini with no Google key configured, the
    deterministic capability filter must drop it — never a soft/AI-only
    guarantee."""
    store, run = _make_store_and_run(session)
    router = ModelRouter(
        providers={"fake": FakeMisbehavingPlannerProvider()},
        routes={"research_planning": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )
    capabilities = ResearchCapabilities(configured_ai_surfaces=frozenset({"chatgpt"}), search_configured=True)

    suggestions = await plan_next_tasks(
        session=session,
        router=router,
        research_run_id=run.id,
        agent_run_id=None,
        store_id=store.id,
        budget=_budget(),
        capabilities=capabilities,
    )

    assert len(suggestions) == 1
    assert suggestions[0].task_type.value == "competitor_deep_dive"


async def test_plan_next_tasks_prompt_lists_unavailable_surfaces(session):
    store, run = _make_store_and_run(session)
    captured_messages = {}

    class CapturingProvider(FakePlannerProvider):
        async def generate(self, request: AIRequest) -> AIResponse:
            captured_messages["messages"] = request.messages
            return await super().generate(request)

    router = ModelRouter(
        providers={"fake": CapturingProvider()},
        routes={"research_planning": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )
    capabilities = ResearchCapabilities(configured_ai_surfaces=frozenset({"chatgpt"}), search_configured=True)

    await plan_next_tasks(
        session=session,
        router=router,
        research_run_id=run.id,
        agent_run_id=None,
        store_id=store.id,
        budget=_budget(),
        capabilities=capabilities,
    )

    user_message = next(m for m in captured_messages["messages"] if m.role.value == "user")
    assert "ai_visibility_gemini" in user_message.content
    assert "ai_visibility_claude" in user_message.content
