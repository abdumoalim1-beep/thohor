"""Part 2 MVP — run_visibility_run against a fake AIProvider. Covers: every
active question gets an EngineAnswer row, sources from a web_search-style
response are stored inline, a provider failure produces a 'failed' row
instead of aborting the run, and an inactive question is never run."""

import json

from sqlmodel import select

from app.ai_visibility.multi_engine_runner import (
    AI_ENGINE_MAX_QUESTIONS,
    ANSWER_ENGINES,
    GOOGLE_SEARCH_MAX_QUESTIONS,
    create_pending_visibility_run,
    run_visibility_run,
)
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.models.visibility_run import EngineAnswer, VisibilityQuestion
from app.providers.ai.base import AIProvider, AIProviderError, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelRouter
from app.providers.search.base import SearchProvider, SearchRequest, SearchResponse


class FakeAnswerProvider(AIProvider):
    name = "openai"  # matches ANSWER_ENGINES' configured provider name

    def __init__(self, answer: str = "إجابة تجريبية", sources: list[dict] | None = None, raise_error: bool = False):
        self._answer = answer
        self._sources = sources or []
        self._raise_error = raise_error

    async def generate(self, request: AIRequest) -> AIResponse:
        if self._raise_error:
            raise AIProviderError("engine unavailable")
        return AIResponse(
            provider=self.name, model=request.model, text=self._answer,
            usage=AIUsage(input_tokens=5, output_tokens=5), sources=self._sources,
        )


def _make_store_with_questions(session, count=2):
    org = Organization(name="t", slug="t-runner")
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

    for i in range(count):
        session.add(VisibilityQuestion(
            store_id=store.id, text=f"سؤال {i}", category="best",
            normalized_text=f"سؤال {i}", source_research_run_id=run.id,
        ))
    session.add(VisibilityQuestion(
        store_id=store.id, text="سؤال معطل", category="best", normalized_text="سؤال معطل",
        source_research_run_id=run.id, is_active=False,
    ))
    session.commit()
    return store


def _router(provider: AIProvider) -> ModelRouter:
    return ModelRouter(providers={"openai": provider}, routes={})


async def test_every_active_question_gets_an_answer_row_and_inactive_is_skipped(session):
    store = _make_store_with_questions(session, count=2)
    provider = FakeAnswerProvider(answer="فلاوري خيار جيد", sources=[{"url": "https://a.example", "title": "A"}])

    pending = create_pending_visibility_run(session, store.id)
    run = await run_visibility_run(session=session, router=_router(provider), run=pending)

    assert run.status == "completed"
    assert run.engines_attempted == [e.engine for e in ANSWER_ENGINES]
    answers = session.exec(select(EngineAnswer).where(EngineAnswer.visibility_run_id == run.id)).all()
    assert len(answers) == 2  # 2 active questions x 1 engine, inactive question excluded
    assert all(a.status == "success" for a in answers)
    assert all(a.raw_answer == "فلاوري خيار جيد" for a in answers)
    assert all(a.sources == [{"url": "https://a.example", "title": "A"}] for a in answers)


async def test_provider_failure_produces_a_failed_row_never_aborts_the_run(session):
    store = _make_store_with_questions(session, count=2)
    provider = FakeAnswerProvider(raise_error=True)

    pending = create_pending_visibility_run(session, store.id)
    run = await run_visibility_run(session=session, router=_router(provider), run=pending)

    assert run.status == "completed"
    answers = session.exec(select(EngineAnswer).where(EngineAnswer.visibility_run_id == run.id)).all()
    assert len(answers) == 2
    assert all(a.status == "failed" for a in answers)
    assert all(a.raw_answer is None for a in answers)


async def test_zero_configured_engines_is_an_honest_empty_run_not_an_error(session):
    store = _make_store_with_questions(session, count=2)
    router = ModelRouter(providers={}, routes={})  # nothing configured

    pending = create_pending_visibility_run(session, store.id)
    run = await run_visibility_run(session=session, router=router, run=pending)

    assert run.status == "completed"
    assert run.engines_attempted == []
    answers = session.exec(select(EngineAnswer).where(EngineAnswer.visibility_run_id == run.id)).all()
    assert answers == []


async def test_ai_engine_run_capped_at_60_even_with_a_larger_backlog(session):
    """90-search re-scope: a store with more than 60 accumulated active
    questions (e.g. after several weekly reruns) must still only run 60
    through the AI engine per visibility run, never the whole backlog."""
    store = _make_store_with_questions(session, count=AI_ENGINE_MAX_QUESTIONS + 15)
    provider = FakeAnswerProvider(answer="فلاوري خيار جيد")

    pending = create_pending_visibility_run(session, store.id)
    run = await run_visibility_run(session=session, router=_router(provider), run=pending)

    answers = session.exec(select(EngineAnswer).where(EngineAnswer.visibility_run_id == run.id)).all()
    assert len(answers) == AI_ENGINE_MAX_QUESTIONS


async def test_total_operations_planned_is_90_when_both_engines_have_enough_questions(session):
    store = _make_store_with_questions(session, count=AI_ENGINE_MAX_QUESTIONS + 20)
    provider = FakeAnswerProvider(answer="فلاوري خيار جيد")
    search_provider = _NoOpSearchProvider()

    pending = create_pending_visibility_run(session, store.id)
    run = await run_visibility_run(session=session, router=_router(provider), run=pending, search_provider=search_provider)

    assert run.total_operations_planned == AI_ENGINE_MAX_QUESTIONS + GOOGLE_SEARCH_MAX_QUESTIONS  # 60 + 30 = 90
    assert run.questions_count == AI_ENGINE_MAX_QUESTIONS


async def test_answers_are_committed_progressively_not_only_after_the_whole_batch(session):
    """A real bug this would catch: if _answer_one_question stopped
    committing its own row, this test's mid-flight snapshot would see 0
    rows even though several calls had already finished — the whole point
    of 'save each result as soon as it completes'. Uses a provider that
    tracks how many EngineAnswer rows already exist in the DB *at the
    moment each call runs*, proving earlier calls' rows were already
    visible before the batch as a whole finished."""
    store = _make_store_with_questions(session, count=5)
    seen_counts_mid_flight: list[int] = []

    class TrackingProvider(FakeAnswerProvider):
        async def generate(self, request):
            seen_counts_mid_flight.append(len(session.exec(select(EngineAnswer)).all()))
            return await super().generate(request)

    provider = TrackingProvider(answer="فلاوري خيار جيد")
    pending = create_pending_visibility_run(session, store.id)
    await run_visibility_run(session=session, router=_router(provider), run=pending, max_concurrency=1)

    # With max_concurrency=1, calls run strictly one at a time, so by the
    # time the Nth call starts, exactly N-1 rows must already be committed
    # — impossible under the old 'commit once after the whole gather' design.
    assert seen_counts_mid_flight == [0, 1, 2, 3, 4]


class _NoOpSearchProvider(SearchProvider):
    name = "noop_search"

    async def search(self, request: SearchRequest) -> SearchResponse:
        return SearchResponse(provider=self.name, results=[])


async def test_peak_concurrency_never_exceeds_the_configured_limit(session):
    """Direct proof that 'never more than N in flight' actually holds —
    not just that the semaphore constant is set to 8, but that the real
    gather() over many questions never lets more than max_concurrency
    calls be mid-flight (sleeping, in this fake) at once."""
    import asyncio

    store = _make_store_with_questions(session, count=20)
    in_flight = 0
    peak = 0

    class ConcurrencyTrackingProvider(FakeAnswerProvider):
        async def generate(self, request):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return await super().generate(request)

    provider = ConcurrencyTrackingProvider(answer="فلاوري خيار جيد")
    pending = create_pending_visibility_run(session, store.id)
    await run_visibility_run(session=session, router=_router(provider), run=pending, max_concurrency=4)

    assert peak <= 4
    assert peak > 1  # sanity check the test actually exercised real overlap, not accidental serialization
