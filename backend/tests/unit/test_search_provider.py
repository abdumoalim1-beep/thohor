import httpx
import pytest

import app.providers.search.serpapi_provider as serpapi_module
from app.providers.search.base import SearchProviderError, SearchRequest
from app.providers.search.mock_provider import MockSearchProvider
from app.providers.search.serpapi_provider import SerpApiProvider


async def test_mock_search_provider_returns_requested_count():
    provider = MockSearchProvider()
    response = await provider.search(
        SearchRequest(keyword="عطر رجالي", country="sa", language="ar", num_results=5)
    )

    assert len(response.results) == 5
    assert response.results[0].rank == 1
    assert response.provider == "mock"


async def test_serpapi_provider_parses_organic_results_and_strips_api_key(monkeypatch):
    fake_payload = {
        "organic_results": [
            {"position": 1, "link": "https://example.com/a", "title": "A"},
            {"position": 2, "link": "https://competitor.com/b", "title": "B"},
        ],
        "search_parameters": {"engine": "google", "api_key": "should-be-stripped"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_payload)

    transport = httpx.MockTransport(handler)
    original_async_client = serpapi_module.httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(serpapi_module.httpx, "AsyncClient", fake_async_client)

    provider = SerpApiProvider(api_key="test-key")
    response = await provider.search(SearchRequest(keyword="test", country="sa", language="ar"))

    assert len(response.results) == 2
    assert response.results[0].domain == "example.com"
    assert response.results[1].domain == "competitor.com"
    assert response.raw["search_parameters"].get("api_key") is None


def _patch_async_client(monkeypatch, transport):
    original_async_client = serpapi_module.httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(serpapi_module.httpx, "AsyncClient", fake_async_client)


async def test_serpapi_provider_retries_on_429_then_succeeds(monkeypatch):
    """Part H5 — a rate-limited response is retried instead of failing the
    query outright."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(429, json={"error": "Too Many Requests"})
        return httpx.Response(200, json={"organic_results": [{"position": 1, "link": "https://x.test", "title": "X"}]})

    _patch_async_client(monkeypatch, httpx.MockTransport(handler))
    import app.core.retry as retry_module
    monkeypatch.setattr(retry_module, "asyncio", type("_A", (), {"sleep": staticmethod(lambda _s: _no_sleep())})())

    provider = SerpApiProvider(api_key="test-key")
    response = await provider.search(SearchRequest(keyword="test", country="sa", language="ar"))

    assert attempts["count"] == 3
    assert len(response.results) == 1


async def _no_sleep():
    return None


async def test_serpapi_provider_does_not_retry_on_401(monkeypatch):
    """Part H5 — an auth error is not transient; retrying wastes time and
    never succeeds, so it must fail on the first attempt."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(401, json={"error": "Invalid API key"})

    _patch_async_client(monkeypatch, httpx.MockTransport(handler))

    provider = SerpApiProvider(api_key="bad-key")
    with pytest.raises(SearchProviderError):
        await provider.search(SearchRequest(keyword="test", country="sa", language="ar"))

    assert attempts["count"] == 1


async def test_serpapi_provider_raises_search_provider_error_when_retries_exhausted(monkeypatch):
    """Part H5 — persistent rate-limiting (e.g. a genuinely exhausted
    monthly quota, not a transient burst) still fails clearly after a
    bounded number of attempts, never hangs or silently returns nothing."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(429, json={"error": "Your account has run out of searches."})

    _patch_async_client(monkeypatch, httpx.MockTransport(handler))
    import app.core.retry as retry_module
    monkeypatch.setattr(retry_module, "asyncio", type("_A", (), {"sleep": staticmethod(lambda _s: _no_sleep())})())

    provider = SerpApiProvider(api_key="test-key")
    with pytest.raises(SearchProviderError):
        await provider.search(SearchRequest(keyword="test", country="sa", language="ar"))

    assert attempts["count"] == 3  # bounded — not an infinite retry loop
