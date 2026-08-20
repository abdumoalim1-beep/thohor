from pydantic import BaseModel
from sqlmodel import select

from app.models.ai_execution import AIExecution, AIExecutionStatus
from app.providers.ai.base import (
    AIMessage,
    AIProviderError,
    AIRequest,
    AIResponse,
    AIRole,
    AIUsage,
)
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


class _CountingSourcedProvider:
    """Simulates a web_search-style response (real text + citations) and
    counts real calls, so a test can assert a cache hit skipped one."""

    name = "sourced"

    def __init__(self):
        self.call_count = 0

    async def generate(self, request: AIRequest) -> AIResponse:
        self.call_count += 1
        return AIResponse(
            provider=self.name,
            model=request.model,
            text=f"real answer #{self.call_count}",
            sources=[{"url": "https://real-result.example", "title": "Real"}],
            web_search_used=True,
            usage=AIUsage(input_tokens=7, output_tokens=7),
        )


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


async def test_execute_single_with_cache_reuses_real_text_and_sources(session):
    """The opt-in path _run_ai_query uses — a byte-identical question asked
    twice must hit the real provider only once, and the second (cached)
    response must carry the SAME real text/sources/web_search_used, not an
    empty stand-in (that would silently zero out a query's signal)."""
    provider = _CountingSourcedProvider()
    router = ModelRouter(providers={"sourced": provider})
    messages = [AIMessage(role=AIRole.user, content="أفضل مسبح")]

    first = await router.execute_single(
        session=session, provider_name="sourced", model="m", task_type="preview_visibility_answering",
        messages=messages, prompt_version="v1", use_cache=True,
    )
    second = await router.execute_single(
        session=session, provider_name="sourced", model="m", task_type="preview_visibility_answering",
        messages=messages, prompt_version="v1", use_cache=True,
    )

    assert provider.call_count == 1  # second call was a real cache hit
    assert second.text == first.text == "real answer #1"
    assert second.sources == first.sources == [{"url": "https://real-result.example", "title": "Real"}]
    assert second.web_search_used is True

    logged = session.exec(select(AIExecution)).all()
    assert len(logged) == 1  # no new row for the cache hit


async def test_execute_single_without_cache_flag_still_never_caches_a_sourced_call(session):
    """use_cache defaults to False — a caller that doesn't opt in (every
    existing caller) must keep getting a fresh real call every time, cache
    storage format change notwithstanding."""
    provider = _CountingSourcedProvider()
    router = ModelRouter(providers={"sourced": provider})
    messages = [AIMessage(role=AIRole.user, content="أفضل مسبح")]

    await router.execute_single(
        session=session, provider_name="sourced", model="m", task_type="preview_visibility_answering", messages=messages
    )
    await router.execute_single(
        session=session, provider_name="sourced", model="m", task_type="preview_visibility_answering", messages=messages
    )

    assert provider.call_count == 2


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
