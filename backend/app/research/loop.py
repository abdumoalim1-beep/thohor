import asyncio
import time
import uuid

from sqlmodel import Session, func, select

from app.core.config import Settings
from app.core.storage import RawArtifactStore
from app.models.base import utcnow
from app.models.research import ResearchRun
from app.models.research_task import DISCOVERY_TASK_TYPES, ResearchTask, TaskStatus, TaskType
from app.models.store import Store
from app.providers.ai.router import ModelRouter
from app.providers.search.base import SearchProvider
from app.research.budget import ResearchBudget
from app.research.cancellation import is_cancellation_requested
from app.research.capabilities import ResearchCapabilities, resolve_research_capabilities
from app.research.executor import TASK_TYPE_WORKERS, TaskContext
from app.research.findings_engine import extract_findings_from_market_map
from app.research.fingerprint import compute_task_fingerprint
from app.research.metrics import ResearchMetrics, compute_research_metrics
from app.research.planner import plan_next_tasks
from app.research.stop_conditions import should_stop_research
from app.research.task_builder import resolve_task_input
from app.research.usage import snapshot_usage

# How often (in completed tasks) to call the AI Planner — bounds its own
# cost rather than invoking it after every single leaf task.
PLANNER_INTERVAL = 3

MARKET_MAP_MOVING_TASK_TYPES = frozenset(
    {TaskType.competitor_discovery_batch, TaskType.competitor_deep_dive, TaskType.page_compare}
)

# Discovered_entities keys that count toward "new competitors found" —
# explicit allow-list rather than guessing across all int keys, since most
# discovered_entities counts (serp_observations, ai_visibility_observations,
# ...) aren't competitors at all.
_COMPETITOR_COUNT_KEYS = frozenset({"unique_competitors"})

# Part G-B4 — deterministic priority dampening: once a task_type has enough
# completed samples in this run to judge, and most of them turned out to be
# dead ends (no new findings/evidence/competitors), new proposals of that
# type get their priority cut before being enqueued. This is the mechanism
# "feed dead-end task tracking back into Planner priority" actually means —
# the Planner (an LLM) is asked not to repeat itself via the prompt, but the
# loop enforces it deterministically regardless of whether the model
# listens, matching this project's 'AI is not the source of truth for
# control decisions' principle used everywhere else.
DEAD_END_MIN_SAMPLES = 2
DEAD_END_USEFULNESS_THRESHOLD = 0.34
DEAD_END_PRIORITY_DAMPENING_FACTOR = 0.5


def _count_new_entities(discovered_entities: dict, extra_findings: int) -> int:
    return sum(v for v in discovered_entities.values() if isinstance(v, int) and not isinstance(v, bool)) + extra_findings


def _task_type_usefulness_rate(session: Session, research_run_id: uuid.UUID, task_type: TaskType) -> float | None:
    """None means 'not enough evidence yet to judge' — callers must treat
    that as 'do not dampen', not as 0."""
    completed = session.exec(
        select(ResearchTask)
        .where(ResearchTask.research_run_id == research_run_id)
        .where(ResearchTask.task_type == task_type)
        .where(ResearchTask.status == TaskStatus.completed)
    ).all()
    if len(completed) < DEAD_END_MIN_SAMPLES:
        return None
    useful_count = sum(1 for t in completed if t.useful)
    return useful_count / len(completed)


async def run_iterative_research_loop(
    *,
    session: Session,
    router: ModelRouter,
    storage: RawArtifactStore,
    search_provider: SearchProvider,
    settings: Settings,
    store: Store,
    run: ResearchRun,
    agent_run_id: uuid.UUID | None,
) -> ResearchMetrics:
    """The Group D2 iterative research loop: seed -> execute -> plan ->
    dedup -> prioritize -> stop-check, repeated until a stop condition
    fires (budget, duration, empty queue, or low new-information rate) —
    never just 'ran out of a fixed list'. Every accepted follow-up task
    traces back to the task that triggered it via parent_task_id."""
    budget = ResearchBudget.from_settings(settings)
    capabilities = resolve_research_capabilities(router, settings)
    start_time = time.monotonic()
    recent_new_entity_counts: list[int] = []
    completed_since_planning = 0
    # Part R2-F1 — only a dedup-fingerprint component, not a measurement
    # locale (real measurement locale comes from the orchestrator's
    # resolved country/language) — but "ar" was still an unexamined
    # Arabic-specific default; "unknown" keeps fingerprints stable without
    # assuming a market.
    locale = store.language or "unknown"
    final_stop_reason = ""

    seed_task = ResearchTask(
        research_run_id=run.id,
        store_id=store.id,
        task_type=TaskType.competitor_discovery_batch,
        reason="seed: mine SERP/AI observations already collected this run for competitors",
        priority=1.0,
        depth=0,
        status=TaskStatus.pending,
        fingerprint=compute_task_fingerprint(TaskType.competitor_discovery_batch, store.url, locale, run.id),
    )
    session.add(seed_task)
    session.commit()

    ctx = TaskContext(
        session=session,
        router=router,
        storage=storage,
        search_provider=search_provider,
        settings=settings,
        store=store,
        run=run,
        agent_run_id=agent_run_id,
    )

    max_concurrency = max(1, settings.research_max_concurrency)

    while True:
        elapsed = time.monotonic() - start_time
        pending_tasks = session.exec(
            select(ResearchTask)
            .where(ResearchTask.research_run_id == run.id)
            .where(ResearchTask.status == TaskStatus.pending)
            .order_by(ResearchTask.priority.desc())  # type: ignore[arg-type]
        ).all()

        # Part H8 — polled fresh every iteration (never cached), since
        # cancellation can be requested by a different process/session at
        # any moment while this batch is running.
        stop, reason = should_stop_research(
            budget=budget,
            elapsed_seconds=elapsed,
            pending_task_count=len(pending_tasks),
            recent_new_entity_counts=recent_new_entity_counts,
            cancellation_requested=is_cancellation_requested(session, run.id),
        )
        if stop:
            final_stop_reason = reason
            break

        # Part H4 — select a BATCH of ready tasks (highest priority first)
        # instead of a single one, sized by both the concurrency ceiling and
        # the remaining task budget — budget is reserved (checked) before
        # dispatch, never discovered as an overshoot afterward. Tasks in a
        # batch have no dependency on each other by construction: a task
        # only ever becomes `pending` once resolve_task_input() already
        # confirmed its inputs exist in the DB (Group D2 design), so
        # "analyze waits for discover" is already satisfied by the time
        # anything reaches this queue — running the batch concurrently
        # never runs a task before what it needs is ready.
        remaining_task_slots = max(0, budget.max_tasks - budget.tasks_used)
        batch_size = min(len(pending_tasks), max_concurrency, remaining_task_slots)
        if batch_size <= 0:
            final_stop_reason = "task budget exhausted"
            break
        batch = pending_tasks[:batch_size]

        for task in batch:
            task.status = TaskStatus.running
            task.started_at = utcnow()
            session.add(task)
        session.commit()

        usage_before = snapshot_usage(session, run.id)

        # Part H7 — every TASK_TYPE_WORKERS function follows the same
        # discipline this refactor establishes throughout Part H5
        # (serp_engine/visibility_engine/gap_engine): session.add() is
        # always immediately followed by session.commit(), never separated
        # by another `await`. That single invariant is what makes sharing
        # one `session` across these concurrently-gathered tasks safe —
        # Python only ever runs one coroutine's bytecode at a time, so two
        # tasks' commits can never actually interleave, and no task is ever
        # "paused mid-await" holding uncommitted state another task's
        # session.rollback() (below) could accidentally wipe.
        async def _run_one(task: ResearchTask):
            worker = TASK_TYPE_WORKERS.get(task.task_type)
            if worker is None:
                return task, None, f"لا يوجد worker لنوع المهمة {task.task_type.value}"
            try:
                result = await worker(ctx, task)
                return task, result, None
            except Exception as exc:  # noqa: BLE001 — one task failing must not fail the batch
                session.rollback()
                return task, None, str(exc)[:500]

        batch_outcomes = await asyncio.gather(*(_run_one(task) for task in batch))

        usage_after = snapshot_usage(session, run.id)
        batch_search = usage_after["search_count"] - usage_before["search_count"]
        batch_ai = usage_after["ai_count"] - usage_before["ai_count"]
        batch_tokens = usage_after["tokens"] - usage_before["tokens"]
        batch_cost = (usage_after["ai_cost"] + usage_after["search_cost"]) - (
            usage_before["ai_cost"] + usage_before["search_cost"]
        )
        succeeded = [(task, result) for task, result, _ in batch_outcomes if result is not None]
        # Part H4 — concurrent tasks share one usage-snapshot delta; exact
        # per-task attribution isn't recoverable once real calls interleave,
        # so each succeeded task's own `cost` is an even split of the
        # batch total — an approximation, clearly not used for budget
        # enforcement (that stays exact, see the aggregate record_task call
        # below). This is the standard trade-off any concurrent-batch
        # system makes without per-call task tagging in the execution ledger.
        per_task_cost = (batch_cost / len(succeeded)) if succeeded else 0.0

        newest_completed_task: ResearchTask | None = None

        for task, result, error in batch_outcomes:
            if result is None:
                task.status = TaskStatus.failed
                task.result_summary = error
                task.completed_at = utcnow()
                session.add(task)
                session.commit()
                recent_new_entity_counts.append(0)
                continue

            task.status = TaskStatus.completed
            task.completed_at = utcnow()
            task.result_summary = result.result_summary
            task.discovered_entities = result.discovered_entities
            task.evidence_ids = result.evidence_ids
            task.cost = per_task_cost
            session.add(task)
            session.commit()
            session.refresh(task)

            new_findings = (
                extract_findings_from_market_map(session, store.id, run.id, origin_task_id=task.id)
                if task.task_type in MARKET_MAP_MOVING_TASK_TYPES
                else []
            )
            new_entity_count = _count_new_entities(result.discovered_entities, len(new_findings))
            recent_new_entity_counts.append(new_entity_count)
            completed_since_planning += 1

            # Part G-B4 — persist the same per-task signal the loop just used
            # to judge itself, so it's queryable later (evaluation harness)
            # and so future planning rounds in *this* run can dampen task
            # types that keep coming back empty (see _task_type_usefulness_rate).
            task.new_findings_count = len(new_findings)
            task.new_evidence_count = len(result.evidence_ids)
            task.new_competitors_count = sum(
                v
                for k, v in result.discovered_entities.items()
                if k in _COMPETITOR_COUNT_KEYS and isinstance(v, int) and not isinstance(v, bool)
            )
            task.useful = new_entity_count > 0
            session.add(task)
            session.commit()

            newest_completed_task = task

        pages_in_batch = sum(
            1 for task, _ in succeeded if task.task_type in (TaskType.competitor_deep_dive, TaskType.page_compare)
        )
        if succeeded:
            budget.record_task(
                search_requests=batch_search,
                ai_requests=batch_ai,
                pages=pages_in_batch,
                tokens=batch_tokens,
                cost_usd=batch_cost,
                tasks_completed=len(succeeded),
            )

        if newest_completed_task is None:
            # The whole batch failed — nothing to plan from, try the next batch.
            continue

        remaining_pending_count = session.exec(
            select(func.count())
            .select_from(ResearchTask)
            .where(ResearchTask.research_run_id == run.id)
            .where(ResearchTask.status == TaskStatus.pending)
        ).one()
        # Interval-gating alone would mean the Planner never runs at all in
        # the common case (a single seed task with no siblings) — the queue
        # goes empty before PLANNER_INTERVAL completions accumulate, and the
        # loop would stop having never asked "what next?". Also plan when
        # the queue is about to run dry, regardless of the interval.
        should_plan = completed_since_planning >= PLANNER_INTERVAL or remaining_pending_count == 0

        if should_plan and newest_completed_task.depth < budget.max_depth and budget.has_capacity():
            completed_since_planning = 0
            try:
                suggestions = await plan_next_tasks(
                    session=session,
                    router=router,
                    research_run_id=run.id,
                    agent_run_id=agent_run_id,
                    store_id=store.id,
                    budget=budget,
                    capabilities=capabilities,
                )
            except Exception:  # noqa: BLE001 — a planning failure just means no new tasks this round
                session.rollback()
                suggestions = []

            for suggestion in suggestions:
                if suggestion.task_type not in DISCOVERY_TASK_TYPES:
                    continue
                if not capabilities.is_task_type_available(suggestion.task_type):
                    continue
                child_depth = newest_completed_task.depth + 1
                if child_depth > budget.max_depth:
                    continue

                fingerprint = compute_task_fingerprint(suggestion.task_type, suggestion.target, locale, run.id)
                existing = session.exec(
                    select(ResearchTask)
                    .where(ResearchTask.research_run_id == run.id)
                    .where(ResearchTask.fingerprint == fingerprint)
                ).first()
                if existing is not None:
                    session.add(
                        ResearchTask(
                            research_run_id=run.id,
                            parent_task_id=newest_completed_task.id,
                            store_id=store.id,
                            task_type=suggestion.task_type,
                            reason=suggestion.reason,
                            hypothesis=suggestion.hypothesis,
                            priority=suggestion.priority,
                            depth=child_depth,
                            status=TaskStatus.skipped_duplicate,
                            fingerprint=fingerprint,
                            result_summary=f"مكرر لمهمة سابقة {existing.id}",
                        )
                    )
                    session.commit()
                    continue

                resolved_input = resolve_task_input(session, store.id, run.id, suggestion)
                if resolved_input is None:
                    continue

                priority = suggestion.priority
                usefulness_rate = _task_type_usefulness_rate(session, run.id, suggestion.task_type)
                if usefulness_rate is not None and usefulness_rate < DEAD_END_USEFULNESS_THRESHOLD:
                    priority *= DEAD_END_PRIORITY_DAMPENING_FACTOR

                session.add(
                    ResearchTask(
                        research_run_id=run.id,
                        parent_task_id=newest_completed_task.id,
                        store_id=store.id,
                        task_type=suggestion.task_type,
                        reason=suggestion.reason,
                        hypothesis=suggestion.hypothesis,
                        priority=priority,
                        depth=child_depth,
                        status=TaskStatus.pending,
                        fingerprint=fingerprint,
                        input=resolved_input,
                    )
                )
                newest_completed_task.created_tasks_count += 1
                session.add(newest_completed_task)
                session.commit()

    duration = time.monotonic() - start_time
    return compute_research_metrics(session, run.id, duration_seconds=duration, stop_reason=final_stop_reason)
