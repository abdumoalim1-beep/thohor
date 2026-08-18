"""Part H9 — the consolidated proof suite for the 10 concurrency
properties the directive requires (all Mock/Replay, no real network/API
calls). Rather than re-implementing every scenario from scratch, this file
is the single place that maps each of the 10 to where it is actually
proven, adding new coverage only for the ones nothing else already proves
end-to-end.

 1. Independent tasks start before others finish (real overlap, not
    strictly sequential)
    -> tests/unit/test_research_loop.py::test_loop_dispatches_independent_tasks_in_a_concurrent_batch
    -> tests/unit/test_multi_store.py::test_run_store_runs_concurrently_overlaps_within_the_limit
 2. A dependency task never starts before its parent
    -> test_dependent_task_never_starts_before_its_parent_completes (below, new)
 3. Concurrency limit is never exceeded
    -> tests/unit/test_serp_engine.py (ConcurrencyTrackingProvider)
    -> tests/unit/test_visibility_engine.py (ConcurrencyTrackingProvider)
    -> tests/unit/test_multi_store.py::test_run_store_runs_concurrently_never_exceeds_the_concurrency_limit
 4. Provider-specific limits work (SERP/AI/etc. bounded independently)
    -> tests/unit/test_serp_engine.py, tests/unit/test_visibility_engine.py
       (each provider's own max_concurrency, proven independently of the
       others via separate semaphores per app.serp.serp_engine._fetch_one /
       app.ai_visibility.visibility_engine's equivalent)
 5. Retries/backoff work
    -> tests/unit/test_retry.py (the generic utility)
    -> tests/unit/test_search_provider.py (SerpAPI adapter)
    -> tests/unit/test_ai_provider_retry.py (OpenAI/Anthropic/Google adapters)
 6. One non-critical task failing doesn't fail the whole batch
    -> test_one_failing_task_does_not_fail_the_rest_of_the_batch (below, new)
 7. Budget blocks over-dispatch (reserved before dispatch, never an
    after-the-fact overshoot)
    -> test_batch_size_is_capped_by_remaining_task_budget_before_dispatch (below, new)
    -> tests/unit/test_research_loop.py::test_loop_stops_when_task_budget_exhausted
       (budget stops the *next* batch entirely)
 8. Retry never produces a duplicate observation
    -> tests/unit/test_executor.py::test_execute_search_google_is_idempotent_on_redispatch
    -> tests/unit/test_executor.py::test_execute_ai_visibility_chatgpt_is_idempotent_on_redispatch
    -> tests/integration/test_orchestrator.py::test_execute_run_is_idempotent_on_redispatch_of_the_same_run
 9. Cancellation blocks new task dispatch
    -> tests/unit/test_research_loop.py::test_loop_stops_dispatching_once_cancellation_is_requested_mid_run
    -> tests/integration/test_orchestrator.py::test_execute_run_marks_cancelled_when_cancellation_requested_before_the_loop
10. Multiple Store Runs can execute concurrently
    -> tests/unit/test_multi_store.py (all tests)
"""

import json

from sqlmodel import select

from app.competitors.discovery_engine import get_or_create_competitor
from app.models.competitor import CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.intent import Intent
from app.models.research_task import ResearchTask, TaskStatus, TaskType
from app.models.serp import SerpObservation
from app.page_intelligence import gap_engine as gap_engine_module
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute
from app.research import loop as loop_module
from app.research.loop import run_iterative_research_loop
from tests.unit.test_research_loop import (
    COMPETITOR_HTML,
    FakePlannerProvider,
    NullSearchProvider,
    ThreeCompetitorPlannerProvider,
    _FakeStorage,
    _make_settings,
    _seed_store_with_serp_observation,
)


def _seed_three_independent_competitors(session, store, run):
    """Same seeding app.research.loop's ThreeCompetitorPlannerProvider test
    (H4) uses: three domains each need a real CompetitorRelationship for
    app.research.task_builder.resolve_task_input to resolve the Planner's
    competitor_deep_dive proposals into dispatchable tasks."""
    intent = session.exec(select(Intent).where(Intent.research_run_id == run.id)).one()
    for domain in ("rival-a.co", "rival-b.co", "rival-c.co"):
        competitor = get_or_create_competitor(
            session, store_id=store.id, domain=domain, competitor_type=CompetitorType.search_competitor,
            research_run_id=run.id,
        )
        session.add(
            CompetitorRelationship(
                competitor_id=competitor.id, intent_id=intent.id, research_run_id=run.id,
                source=RelationshipSource.serp, rank_or_position=1,
            )
        )
    session.commit()
    serp_obs = session.exec(select(SerpObservation).where(SerpObservation.research_run_id == run.id)).one()
    serp_obs.results = serp_obs.results + [
        {"rank": 2, "domain": "rival-a.co", "url": "https://rival-a.co/x"},
        {"rank": 3, "domain": "rival-b.co", "url": "https://rival-b.co/x"},
        {"rank": 4, "domain": "rival-c.co", "url": "https://rival-c.co/x"},
    ]
    session.add(serp_obs)
    session.commit()


async def test_dependent_task_never_starts_before_its_parent_completes(session, monkeypatch):
    """Scenario 2 — a child task's own started_at can never be earlier than
    the parent task's completed_at, since children are only ever created
    (as `pending`) by the Planner *after* the parent's batch has already
    been fully processed (app.research.loop: planning happens after the
    batch loop, never inside it)."""
    store, run = _seed_store_with_serp_observation(session)

    async def fake_safe_fetch(url, policy):
        from app.crawler.fetch import FetchResult

        return FetchResult(url=url, status_code=200, content_type="text/html", text=COMPETITOR_HTML)

    monkeypatch.setattr(gap_engine_module, "safe_fetch", fake_safe_fetch)
    monkeypatch.setattr(loop_module, "PLANNER_INTERVAL", 1)

    class FakeGapProvider(AIProvider):
        name = "gap"

        async def generate(self, request: AIRequest) -> AIResponse:
            payload = json.dumps(
                {"gaps": ["فجوة"], "recommendation_summary": "أضف محتوى.", "confidence": 0.7}
            )
            return AIResponse(
                provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=10, output_tokens=10)
            )

    router = ModelRouter(
        providers={"planner": FakePlannerProvider(), "gap": FakeGapProvider()},
        routes={
            "research_planning": TaskRoute(primary=ModelChoice("planner", "fake-model")),
            "page_gap_analysis": TaskRoute(primary=ModelChoice("gap", "fake-model")),
        },
    )

    await run_iterative_research_loop(
        session=session, router=router, storage=_FakeStorage(), search_provider=NullSearchProvider(),
        settings=_make_settings(), store=store, run=run, agent_run_id=None,
    )

    tasks = session.exec(select(ResearchTask).where(ResearchTask.research_run_id == run.id)).all()
    seed = next(t for t in tasks if t.task_type == TaskType.competitor_discovery_batch)
    child = next(t for t in tasks if t.task_type == TaskType.competitor_deep_dive and t.status == TaskStatus.completed)

    assert child.parent_task_id == seed.id
    assert seed.completed_at is not None and child.started_at is not None
    assert seed.completed_at <= child.started_at


async def test_one_failing_task_does_not_fail_the_rest_of_the_batch(session, monkeypatch):
    """Scenario 6 — three independent competitor_deep_dive tasks dispatched
    in the same concurrent batch; one competitor's page fetch fails. The
    other two must still complete normally, and the loop itself must not
    crash or abort."""
    store, run = _seed_store_with_serp_observation(session)
    _seed_three_independent_competitors(session, store, run)

    async def flaky_safe_fetch(url, policy):
        from app.crawler.fetch import FetchResult

        if "rival-b.co" in url:
            raise RuntimeError("simulated network failure for rival-b.co")
        return FetchResult(url=url, status_code=200, content_type="text/html", text=COMPETITOR_HTML)

    monkeypatch.setattr(gap_engine_module, "safe_fetch", flaky_safe_fetch)
    monkeypatch.setattr(loop_module, "PLANNER_INTERVAL", 1)

    class FakeGapProvider(AIProvider):
        name = "gap"

        async def generate(self, request: AIRequest) -> AIResponse:
            payload = json.dumps(
                {"gaps": ["فجوة"], "recommendation_summary": "أضف محتوى.", "confidence": 0.7}
            )
            return AIResponse(
                provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=10, output_tokens=10)
            )

    router = ModelRouter(
        providers={"planner": ThreeCompetitorPlannerProvider(), "gap": FakeGapProvider()},
        routes={
            "research_planning": TaskRoute(primary=ModelChoice("planner", "fake-model")),
            "page_gap_analysis": TaskRoute(primary=ModelChoice("gap", "fake-model")),
        },
    )

    metrics = await run_iterative_research_loop(
        session=session, router=router, storage=_FakeStorage(), search_provider=NullSearchProvider(),
        settings=_make_settings(research_max_concurrency=3), store=store, run=run, agent_run_id=None,
    )

    tasks = session.exec(
        select(ResearchTask)
        .where(ResearchTask.research_run_id == run.id)
        .where(ResearchTask.task_type == TaskType.competitor_deep_dive)
    ).all()
    completed = [t for t in tasks if t.status == TaskStatus.completed]
    failed = [t for t in tasks if t.status == TaskStatus.failed]

    assert len(completed) == 2
    assert len(failed) == 1
    assert metrics.total_tasks == 4  # seed + 3 deep dives (2 completed, 1 failed) — the loop itself never crashed


async def test_batch_size_is_capped_by_remaining_task_budget_before_dispatch(session, monkeypatch):
    """Scenario 7 — the task budget is reserved (checked) *before*
    dispatch, never discovered as an overshoot afterward: with only 1 task
    slot remaining after the seed, a batch of 3 independently-proposed
    tasks must be sized down to exactly 1, never launch 3 and cancel 2."""
    store, run = _seed_store_with_serp_observation(session)
    _seed_three_independent_competitors(session, store, run)
    monkeypatch.setattr(loop_module, "PLANNER_INTERVAL", 1)

    router = ModelRouter(
        providers={"planner": ThreeCompetitorPlannerProvider()},
        routes={"research_planning": TaskRoute(primary=ModelChoice("planner", "fake-model"))},
    )

    # max_tasks=2: the seed consumes 1 slot, leaving exactly 1 for the 3
    # independently-proposed competitor_deep_dive tasks.
    metrics = await run_iterative_research_loop(
        session=session, router=router, storage=_FakeStorage(), search_provider=NullSearchProvider(),
        settings=_make_settings(research_max_tasks=2, research_max_concurrency=10), store=store, run=run,
        agent_run_id=None,
    )

    tasks = session.exec(
        select(ResearchTask)
        .where(ResearchTask.research_run_id == run.id)
        .where(ResearchTask.task_type == TaskType.competitor_deep_dive)
    ).all()
    # All 3 proposals from the one Planner round are persisted as `pending`
    # rows (creation isn't budget-gated) — but only as many as the
    # remaining task budget allows are ever actually dispatched
    # (running/completed/failed). The other 2 stay `pending` forever: the
    # loop's next stop-check sees the budget exhausted and never revisits
    # them, proving the reservation happened before dispatch, not as a
    # discovered-after-the-fact overshoot.
    assert len(tasks) == 3
    dispatched = [t for t in tasks if t.status in (TaskStatus.running, TaskStatus.completed, TaskStatus.failed)]
    still_pending = [t for t in tasks if t.status == TaskStatus.pending]
    assert len(dispatched) == 1  # exactly the reserved slot, never all 3
    assert len(still_pending) == 2
    assert metrics.total_tasks == 4  # seed (dispatched) + all 3 proposed rows (1 dispatched, 2 forever pending)
