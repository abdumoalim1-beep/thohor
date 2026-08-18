"""Part H5 — retry/backoff for the real AI provider adapters, mirroring
test_search_provider.py's approach: mock the transport layer so each SDK's
own exception mapping (RateLimitError, ClientError, etc.) fires for real,
then verify our retry_with_backoff wrapping reacts correctly."""

import httpx
import pytest

import app.core.retry as retry_module
from app.providers.ai.anthropic_provider import AnthropicProvider
from app.providers.ai.base import AIMessage, AIProviderError, AIRequest, AIRole
from app.providers.ai.google_provider import GoogleProvider
from app.providers.ai.openai_provider import OpenAIProvider


def _no_op_sleep(monkeypatch):
    monkeypatch.setattr(retry_module, "asyncio", type("_A", (), {"sleep": staticmethod(lambda _s: _async_noop())})())


async def _async_noop():
    return None


def _request() -> AIRequest:
    return AIRequest(task_type="classification", model="m", messages=[AIMessage(role=AIRole.user, content="hi")])


def _openai_success_payload():
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


async def test_openai_provider_retries_on_429_then_succeeds(monkeypatch):
    _no_op_sleep(monkeypatch)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(429, json={"error": {"message": "rate limited", "type": "rate_limit_error"}})
        return httpx.Response(200, json=_openai_success_payload())

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from openai import AsyncOpenAI

    provider = OpenAIProvider(api_key="test-key")
    provider._client = AsyncOpenAI(api_key="test-key", max_retries=0, http_client=http_client)

    response = await provider.generate(_request())

    assert attempts["count"] == 3
    assert response.text == "hi"


async def test_openai_provider_does_not_retry_on_401(monkeypatch):
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(401, json={"error": {"message": "invalid api key", "type": "invalid_request_error"}})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from openai import AsyncOpenAI

    provider = OpenAIProvider(api_key="bad-key")
    provider._client = AsyncOpenAI(api_key="bad-key", max_retries=0, http_client=http_client)

    with pytest.raises(AIProviderError):
        await provider.generate(_request())

    assert attempts["count"] == 1


def _anthropic_success_payload():
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5-20251001",
        "content": [{"type": "text", "text": "hi"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


async def test_anthropic_provider_retries_on_overloaded_then_succeeds(monkeypatch):
    _no_op_sleep(monkeypatch)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(
                529, json={"type": "error", "error": {"type": "overloaded_error", "message": "overloaded"}}
            )
        return httpx.Response(200, json=_anthropic_success_payload())

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from anthropic import AsyncAnthropic

    provider = AnthropicProvider(api_key="test-key")
    provider._client = AsyncAnthropic(api_key="test-key", max_retries=0, http_client=http_client)

    response = await provider.generate(_request())

    assert attempts["count"] == 3
    assert response.text == "hi"


async def test_anthropic_provider_does_not_retry_on_401(monkeypatch):
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            401, json={"type": "error", "error": {"type": "authentication_error", "message": "bad key"}}
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from anthropic import AsyncAnthropic

    provider = AnthropicProvider(api_key="bad-key")
    provider._client = AsyncAnthropic(api_key="bad-key", max_retries=0, http_client=http_client)

    with pytest.raises(AIProviderError):
        await provider.generate(_request())

    assert attempts["count"] == 1


async def test_google_provider_retries_on_429_then_succeeds(monkeypatch):
    _no_op_sleep(monkeypatch)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(
                429, json={"error": {"code": 429, "message": "rate limited", "status": "RESOURCE_EXHAUSTED"}}
            )
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "hi"}], "role": "model"}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
            },
        )

    from google import genai
    from google.genai import types

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GoogleProvider(api_key="test-key")
    provider._client = genai.Client(api_key="test-key", http_options=types.HttpOptions(httpxAsyncClient=http_client))

    response = await provider.generate(_request())

    assert attempts["count"] == 3
    assert response.text == "hi"


async def test_google_provider_does_not_retry_on_400(monkeypatch):
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, json={"error": {"code": 400, "message": "bad request", "status": "INVALID_ARGUMENT"}})

    from google import genai
    from google.genai import types

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GoogleProvider(api_key="test-key")
    provider._client = genai.Client(api_key="test-key", http_options=types.HttpOptions(httpxAsyncClient=http_client))

    with pytest.raises(AIProviderError):
        await provider.generate(_request())

    assert attempts["count"] == 1
