"""Stage 5 — bounded search execution. Covers the one piece of real logic
in this module: google_query_limit's index-based gating, which lets the AI
leg run against more queries than Google without a second call site or a
new status value (reuses the existing search_provider=None degradation
path — see run_preview_searches's docstring)."""

import asyncio

from app.core.config import Settings
from app.preview_reports import search
from app.providers.search.base import SearchResponse


class _FakeSearchProvider:
    def __init__(self):
        self.calls: list[str] = []

    async def search(self, request):
        self.calls.append(request.keyword)
        return SearchResponse(provider="fake", results=[])


async def _fake_run_ai_query(router, session, semaphore, query_text, timeout_seconds):
    async with semaphore:
        pass
    return {"status": "success", "raw_result": "", "sources": []}


def test_google_query_limit_only_gates_queries_past_the_limit(monkeypatch):
    monkeypatch.setattr(search, "_run_ai_query", _fake_run_ai_query)

    provider = _FakeSearchProvider()
    queries = [{"query": f"q{i}"} for i in range(5)]
    settings = Settings(preview_search_max_concurrency=10)

    results = asyncio.run(
        search.run_preview_searches(
            router=None,
            session=None,
            queries=queries,
            settings=settings,
            search_provider=provider,
            google_query_limit=3,
        )
    )

    # only the first 3 queries ever reach the real provider
    assert provider.calls == ["q0", "q1", "q2"]
    # google leg for the remaining 2 degrades exactly like an unconfigured
    # provider would (status="failed"), never an exception or a guessed result
    assert [r["google"]["status"] for r in results] == ["success", "success", "success", "failed", "failed"]
    # the AI leg is untouched by the limit — every query still gets checked
    assert all(r["ai"]["status"] == "success" for r in results)


def test_google_query_limit_none_runs_google_for_every_query(monkeypatch):
    monkeypatch.setattr(search, "_run_ai_query", _fake_run_ai_query)

    provider = _FakeSearchProvider()
    queries = [{"query": f"q{i}"} for i in range(3)]
    settings = Settings(preview_search_max_concurrency=10)

    asyncio.run(
        search.run_preview_searches(
            router=None, session=None, queries=queries, settings=settings, search_provider=provider
        )
    )

    assert provider.calls == ["q0", "q1", "q2"]
