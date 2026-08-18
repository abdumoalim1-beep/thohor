from pydantic import BaseModel
from sqlmodel import select

from app.models.ai_execution import AIExecution, AIExecutionStatus
from app.providers.ai.base import AIMessage, AIProviderError, AIRequest, AIResponse, AIRole, AIUsage
from app.providers.ai.mock_provider import MockAIProvider
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute


class FailingProvider:
    name = "failing"

    async def generate(self, request: AIRequest) -> AIResponse:
        raise AIProviderError("simulated provider outage")


class FencedJSONProvider:
    """Reproduces a real observed failure: some models wrap JSON output in a
    ```json ... ``` fence even when told not to."""

    name = "fenced"

    async def generate(self, request: AIRequest) -> AIResponse:
        text = '```json\n{"ok": true, "value": 42}\n```'
        return AIResponse(provider=self.name, model=request.model, text=text, usage=AIUsage(input_tokens=5, output_tokens=5))


class _OkSchema(BaseModel):
    ok: bool
    value: int


async def test_router_executes_and_logs_execution(session):
    router = ModelRouter(
        providers={"mock": MockAIProvider()},
        routes={"classification": TaskRoute(primary=ModelChoice("mock", "mock-model"))},
    )

    response = await router.execute(
        session=session,
        task_type="classification",
        messages=[AIMessage(role=AIRole.user, content="hello")],
        prompt_name="test_prompt",
        prompt_version="v1",
    )

    assert response.provider == "mock"
    assert response.usage.input_tokens == 10

    logged = session.exec(select(AIExecution)).all()
    assert len(logged) == 1
    assert logged[0].status == AIExecutionStatus.success
    assert logged[0].task_type == "classification"
    assert logged[0].prompt_version == "v1"


async def test_router_reuses_cached_execution_without_new_provider_call(session):
    router = ModelRouter(
        providers={"mock": MockAIProvider()},
        routes={"classification": TaskRoute(primary=ModelChoice("mock", "mock-model"))},
    )
    messages = [AIMessage(role=AIRole.user, content="same input every time")]

    await router.execute(session=session, task_type="classification", messages=messages, prompt_version="v1")
    await router.execute(session=session, task_type="classification", messages=messages, prompt_version="v1")

    logged = session.exec(select(AIExecution)).all()
    assert len(logged) == 1  # second call was a cache hit — no new row


async def test_router_falls_back_to_secondary_provider_on_failure(session):
    router = ModelRouter(
        providers={"failing": FailingProvider(), "mock": MockAIProvider()},
        routes={
            "classification": TaskRoute(
                primary=ModelChoice("failing", "broken-model"),
                fallback=ModelChoice("mock", "mock-model"),
            )
        },
    )

    response = await router.execute(
        session=session,
        task_type="classification",
        messages=[AIMessage(role=AIRole.user, content="hello")],
    )

    assert response.provider == "mock"

    logged = session.exec(select(AIExecution)).all()
    statuses = {row.status for row in logged}
    assert AIExecutionStatus.error in statuses
    assert AIExecutionStatus.fallback in statuses


async def test_router_parses_json_wrapped_in_markdown_fence(session):
    router = ModelRouter(
        providers={"fenced": FencedJSONProvider()},
        routes={"classification": TaskRoute(primary=ModelChoice("fenced", "fenced-model"))},
    )

    response = await router.execute(
        session=session,
        task_type="classification",
        messages=[AIMessage(role=AIRole.user, content="hello")],
        response_schema=_OkSchema,
    )

    assert response.parsed == {"ok": True, "value": 42}


async def test_configured_provider_names_excludes_mock():
    router = ModelRouter(providers={"mock": MockAIProvider(), "openai": MockAIProvider()})
    assert router.configured_provider_names == ["openai"]


async def test_execute_single_calls_exact_provider_and_model(session):
    router = ModelRouter(providers={"mock": MockAIProvider()})

    response = await router.execute_single(
        session=session,
        provider_name="mock",
        model="a-specific-model",
        task_type="ai_visibility_probe",
        messages=[AIMessage(role=AIRole.user, content="وش أفضل عطر رجالي للصيف؟")],
    )

    assert response.provider == "mock"

    logged = session.exec(select(AIExecution)).one()
    assert logged.provider == "mock"
    assert logged.model == "a-specific-model"
    assert logged.task_type == "ai_visibility_probe"


async def test_execute_single_never_caches(session):
    router = ModelRouter(providers={"mock": MockAIProvider()})
    messages = [AIMessage(role=AIRole.user, content="same input every time")]

    await router.execute_single(session=session, provider_name="mock", model="m", task_type="ai_visibility_probe", messages=messages)
    await router.execute_single(session=session, provider_name="mock", model="m", task_type="ai_visibility_probe", messages=messages)

    logged = session.exec(select(AIExecution)).all()
    assert len(logged) == 2  # unlike execute(), every call is a fresh sample


async def test_execute_single_raises_and_logs_on_provider_failure(session):
    router = ModelRouter(providers={"failing": FailingProvider()})

    try:
        await router.execute_single(
            session=session,
            provider_name="failing",
            model="broken-model",
            task_type="ai_visibility_probe",
            messages=[AIMessage(role=AIRole.user, content="hello")],
        )
        raised = False
    except AIProviderError:
        raised = True

    assert raised

    logged = session.exec(select(AIExecution)).one()
    assert logged.status == AIExecutionStatus.error
