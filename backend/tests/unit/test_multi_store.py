"""Part H6 — multi-store concurrency. Uses plain in-memory Store/ResearchRun
objects (never persisted) since run_store_runs_concurrently itself is a
pure orchestration primitive — no DB/session involvement at this layer."""

import asyncio
import uuid

import pytest

from app.models.research import ResearchRun, RunStatus
from app.models.store import Store
from app.orchestrator.multi_store import run_store_runs_concurrently


def _make_pairs(n: int) -> list[tuple[Store, ResearchRun]]:
    pairs = []
    for _ in range(n):
        store = Store(id=uuid.uuid4(), organization_id=uuid.uuid4(), url=f"https://store-{uuid.uuid4().hex[:6]}.test")
        run = ResearchRun(id=uuid.uuid4(), store_id=store.id, status=RunStatus.pending)
        pairs.append((store, run))
    return pairs


async def test_run_store_runs_concurrently_overlaps_within_the_limit():
    pairs = _make_pairs(4)
    in_flight = {"count": 0, "peak": 0}

    async def run_one(store: Store, run: ResearchRun) -> ResearchRun:
        in_flight["count"] += 1
        in_flight["peak"] = max(in_flight["peak"], in_flight["count"])
        await asyncio.sleep(0.05)
        in_flight["count"] -= 1
        run.status = RunStatus.completed
        return run

    outcomes = await run_store_runs_concurrently(pairs, run_one, max_concurrency=2)

    assert len(outcomes) == 4
    assert all(o.error is None and o.run is not None for o in outcomes)
    assert in_flight["peak"] == 2  # bounded by max_concurrency, and > 1 proves real overlap


async def test_run_store_runs_concurrently_never_exceeds_the_concurrency_limit():
    pairs = _make_pairs(6)
    in_flight = {"count": 0, "peak": 0}

    async def run_one(store: Store, run: ResearchRun) -> ResearchRun:
        in_flight["count"] += 1
        in_flight["peak"] = max(in_flight["peak"], in_flight["count"])
        await asyncio.sleep(0.02)
        in_flight["count"] -= 1
        return run

    await run_store_runs_concurrently(pairs, run_one, max_concurrency=3)

    assert in_flight["peak"] <= 3


async def test_run_store_runs_concurrently_isolates_one_store_failure():
    pairs = _make_pairs(3)
    failing_store_id = pairs[1][0].id

    async def run_one(store: Store, run: ResearchRun) -> ResearchRun:
        if store.id == failing_store_id:
            raise RuntimeError("boom: crawl blocked by robots.txt")
        run.status = RunStatus.completed
        return run

    outcomes = await run_store_runs_concurrently(pairs, run_one, max_concurrency=3)

    assert len(outcomes) == 3
    by_store = {o.store_id: o for o in outcomes}
    assert by_store[failing_store_id].run is None
    assert "boom" in by_store[failing_store_id].error
    others = [o for o in outcomes if o.store_id != failing_store_id]
    assert all(o.error is None and o.run is not None for o in others)


async def test_run_store_runs_concurrently_preserves_input_order_in_the_result():
    pairs = _make_pairs(5)

    async def run_one(store: Store, run: ResearchRun) -> ResearchRun:
        # Later stores finish first — output order must still match input order.
        await asyncio.sleep(0.01 * (5 - list(p[0] for p in pairs).index(store)))
        return run

    outcomes = await run_store_runs_concurrently(pairs, run_one, max_concurrency=5)

    assert [o.store_id for o in outcomes] == [store.id for store, _ in pairs]


async def test_run_store_runs_concurrently_defaults_to_at_least_one_slot():
    pairs = _make_pairs(2)

    async def run_one(store: Store, run: ResearchRun) -> ResearchRun:
        return run

    outcomes = await run_store_runs_concurrently(pairs, run_one, max_concurrency=0)

    assert len(outcomes) == 2
    assert all(o.error is None for o in outcomes)
