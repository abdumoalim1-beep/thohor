"""Stage 5 (spec) — bounded search execution for a PreviewReport, exactly
two sources: Google (via the existing SearchProvider abstraction) and one
AI source (ChatGPT via web_search). Modeled directly on
app.ai_visibility.multi_engine_runner's _answer_one_question/
_search_one_question_google — same "one call, no route-fallback, a
failure is an ordinary absent result, never an exception" shape, which is
exactly how "one source failing never fails the whole report" is
satisfied here too (reused proven pattern, not new resilience logic).

Deliberately does NOT persist per-query rows the way multi_engine_runner
does (EngineAnswer) — PreviewReport has no intermediate DB state by
design (see app.models.preview_report's docstring). Each query's result
is accumulated into an in-memory list as it completes and returned once
`asyncio.gather` resolves; the caller writes the whole thing into the
report blob's `queries` field in one shot. AIExecution/SerpExecution
ledger rows still get written by the underlying router/provider calls —
that's a separate cost ledger, not report state.

Per spec: `{"status": "failed"}` must never be silently turned into
`brand_found = False` — this module only ever returns raw
results/answers or a bare failed status; brand-appearance detection is a
later, separate, deterministic step (see app.preview_reports.visibility)."""

import asyncio

from sqlmodel import Session

from app.core.config import Settings
from app.prompts.visibility_question_answering import VISIBILITY_QUESTION_ANSWERING_PROMPT
from app.providers.ai.base import AIMessage, AIProviderError, AIRole
from app.providers.ai.router import ModelRouter
from app.providers.search.base import SearchProvider, SearchProviderError, SearchRequest


async def _run_google_query(
    search_provider: SearchProvider,
    semaphore: asyncio.Semaphore,
    query_text: str,
    country: str,
    language: str,
    timeout_seconds: float,
) -> dict:
    async with semaphore:
        try:
            response = await asyncio.wait_for(
                search_provider.search(
                    SearchRequest(keyword=query_text, country=country, language=language, num_results=10)
                ),
                timeout=timeout_seconds,
            )
        except (SearchProviderError, RuntimeError, TimeoutError, asyncio.TimeoutError):
            return {"status": "failed"}
    return {
        "status": "success",
        "results": [
            {"rank": r.rank, "domain": r.domain, "url": r.url, "title": r.title} for r in response.results
        ],
    }


async def _run_ai_query(
    router: ModelRouter,
    session: Session,
    semaphore: asyncio.Semaphore,
    query_text: str,
    timeout_seconds: float,
) -> dict:
    messages = [
        AIMessage(role=AIRole.system, content=VISIBILITY_QUESTION_ANSWERING_PROMPT.system),
        AIMessage(role=AIRole.user, content=query_text),
    ]
    async with semaphore:
        try:
            response = await asyncio.wait_for(
                router.execute_single(
                    session=session,
                    provider_name="openai",
                    model="gpt-4o-mini",
                    task_type="preview_visibility_answering",
                    messages=messages,
                    prompt_name=VISIBILITY_QUESTION_ANSWERING_PROMPT.name,
                    prompt_version=VISIBILITY_QUESTION_ANSWERING_PROMPT.version,
                    enable_web_search=True,
                    # Safe here specifically: the real web_search answer for a
                    # given question text doesn't depend on which store is
                    # asking, so reusing it across two reports that happen to
                    # generate the identical generic query (same category,
                    # e.g. "أفضل مسبح") is a real cost saving, not a shortcut
                    # on accuracy — see ModelRouter.execute_single's
                    # use_cache docstring.
                    use_cache=True,
                ),
                timeout=timeout_seconds,
            )
        except (AIProviderError, RuntimeError, TimeoutError, asyncio.TimeoutError):
            return {"status": "failed"}
    return {"status": "success", "raw_result": response.text, "sources": response.sources or []}


async def _run_one_query(
    *,
    router: ModelRouter,
    session: Session,
    search_provider: SearchProvider | None,
    semaphore: asyncio.Semaphore,
    query: dict,
    country: str,
    language: str,
    google_timeout: float,
    ai_timeout: float,
) -> dict:
    google_task = (
        _run_google_query(search_provider, semaphore, query["query"], country, language, google_timeout)
        if search_provider is not None
        else asyncio.sleep(0, result={"status": "failed"})
    )
    ai_task = _run_ai_query(router, session, semaphore, query["query"], ai_timeout)
    google_result, ai_result = await asyncio.gather(google_task, ai_task)
    return {**query, "google": google_result, "ai": ai_result}


async def run_preview_searches(
    *,
    router: ModelRouter,
    session: Session,
    queries: list[dict],
    settings: Settings,
    search_provider: SearchProvider | None = None,
    country: str = "sa",
    language: str = "ar",
    google_query_limit: int | None = None,
) -> list[dict]:
    """Runs every query in `queries` (from app.preview_reports.queries.
    generate_search_queries) against Google + the one AI engine, under one
    shared semaphore across both sources — never more than
    settings.preview_search_max_concurrency operations in flight at once.
    search_provider=None (e.g. no SerpAPI key configured) degrades every
    query's "google" leg to {"status": "failed"} rather than raising —
    the AI leg still runs normally.

    google_query_limit: when `queries` is longer than Google's own budget
    (the AI leg is allowed a larger query set — see
    settings.preview_search_ai_query_count), queries at/after this index
    reuse the exact same search_provider=None degradation path for their
    google leg — same "absent result, never an exception" behavior as a
    genuinely unconfigured provider, just scoped to the extra queries
    instead of all of them. The AI leg is unaffected and runs for every
    query regardless of this limit."""
    semaphore = asyncio.Semaphore(settings.preview_search_max_concurrency)
    tasks = [
        _run_one_query(
            router=router,
            session=session,
            search_provider=(
                search_provider if google_query_limit is None or index < google_query_limit else None
            ),
            semaphore=semaphore,
            query=query,
            country=country,
            language=language,
            google_timeout=settings.preview_search_google_timeout_seconds,
            ai_timeout=settings.preview_search_ai_timeout_seconds,
        )
        for index, query in enumerate(queries)
    ]
    if not tasks:
        return []
    return list(await asyncio.gather(*tasks))
