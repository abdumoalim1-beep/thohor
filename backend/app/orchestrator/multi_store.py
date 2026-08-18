import asyncio
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlmodel import Session

from app.core.config import Settings
from app.core.db import engine
from app.core.storage import get_storage
from app.models.research import ResearchRun
from app.models.store import Store
from app.orchestrator.research_orchestrator import ResearchOrchestrator
from app.providers.ai import get_router
from app.providers.search import get_search_provider


@dataclass
class StoreRunOutcome:
    store_id: uuid.UUID
    run: ResearchRun | None
    error: str | None


async def run_store_runs_concurrently(
    pairs: list[tuple[Store, ResearchRun]],
    run_one: Callable[[Store, ResearchRun], Awaitable[ResearchRun]],
    max_concurrency: int,
) -> list[StoreRunOutcome]:
    """Part H6 — bounds how many stores' `execute_run` coroutines are in
    flight at once, same semaphore-around-gather shape as the intra-run
    batch dispatch in app.research.loop (Part H4). One store failing never
    aborts the others — each outcome is captured independently, matching
    the loop's per-task isolation.

    Safety note that does NOT apply here the way it does inside one run:
    each `run_one(store, run)` call is expected to own its own Session
    (see run_baseline_for_stores_concurrently below). Concurrent store runs
    touch fully disjoint store_id/research_run_id rows, so — unlike tasks
    sharing one Session within a single run — there is no shared-state
    invariant to maintain across stores; giving each its own Session is
    simply standard SQLAlchemy usage, not a special-case safety measure.
    """
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def _run_one(store: Store, run: ResearchRun) -> StoreRunOutcome:
        async with semaphore:
            try:
                result = await run_one(store, run)
                return StoreRunOutcome(store_id=store.id, run=result, error=None)
            except Exception as exc:  # noqa: BLE001 — isolate one store's failure from the rest of the batch
                return StoreRunOutcome(store_id=store.id, run=None, error=str(exc)[:500])

    return list(await asyncio.gather(*(_run_one(store, run) for store, run in pairs)))


async def run_baseline_for_stores_concurrently(
    store_ids: list[uuid.UUID], settings: Settings, max_concurrency: int | None = None
) -> list[StoreRunOutcome]:
    """The real driver behind Store-level parallelism (point 8.5 of the
    directive): each store gets its own Session/ResearchOrchestrator (never
    one Session shared across stores), bounded by
    Settings.store_run_max_concurrency. Intended for the eventual Live
    Validation round and any other direct (non-Celery) multi-store run —
    Celery's own worker pool (see celery_app.conf.worker_concurrency, also
    tied to this same setting) is what bounds concurrency when runs are
    dispatched one-per-task via execute_research_run_task.delay() instead.
    """

    async def _run_one(store: Store, run: ResearchRun) -> ResearchRun:
        with Session(engine) as session:
            live_store = session.get(Store, store.id)
            live_run = session.get(ResearchRun, run.id)
            orchestrator = ResearchOrchestrator(
                session=session,
                storage=get_storage(),
                router=get_router(),
                search_provider=get_search_provider(session),
                settings=settings,
            )
            return await orchestrator.execute_run(live_store, live_run)

    pairs: list[tuple[Store, ResearchRun]] = []
    with Session(engine) as session:
        for store_id in store_ids:
            store = session.get(Store, store_id)
            if store is None:
                raise ValueError(f"store {store_id} not found")
            run = ResearchOrchestrator.create_pending_run(session, store)
            pairs.append((store, run))

    return await run_store_runs_concurrently(
        pairs, _run_one, max_concurrency or settings.store_run_max_concurrency
    )
