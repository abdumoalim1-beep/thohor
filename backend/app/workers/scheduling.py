import uuid
from datetime import timedelta

from sqlmodel import Session, select

from app.core.cadence import compute_next_scheduled_run_at
from app.models.base import utcnow
from app.models.research import ResearchRunType
from app.models.store import Store, StoreStatus
from app.models.visibility_run import VisibilityQuestion, VisibilityRun
from app.orchestrator.research_orchestrator import ResearchOrchestrator

VISIBILITY_RUN_INTERVAL_DAYS = 7


def dispatch_due_stores(session: Session) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Business logic only — no Celery import here (same 'execution layer
    only' principle as ResearchOrchestrator itself). Finds every active
    store whose next_scheduled_run_at has passed, creates a pending
    monitoring ResearchRun for each, and advances its schedule. The Celery
    task in app/workers/tasks.py is the only thing that actually enqueues
    execution, so this function is fully testable without a broker."""
    now = utcnow()
    due_stores = session.exec(
        select(Store)
        .where(Store.status == StoreStatus.active)
        .where(Store.next_scheduled_run_at.is_not(None))  # type: ignore[union-attr]
        .where(Store.next_scheduled_run_at <= now)  # type: ignore[operator]
    ).all()

    dispatched: list[tuple[uuid.UUID, uuid.UUID]] = []
    for store in due_stores:
        run = ResearchOrchestrator.create_pending_run(session, store, run_type=ResearchRunType.monitoring)
        store.next_scheduled_run_at = compute_next_scheduled_run_at(store.monitoring_cadence, now)
        session.add(store)
        session.commit()
        dispatched.append((store.id, run.id))

    return dispatched


def dispatch_due_visibility_stores(session: Session) -> list[uuid.UUID]:
    """Simple weekly cadence (user-directed re-scope: 'جدولة أسبوعية
    بسيطة') — deliberately not a new Store column/migration: 'due' is
    computed directly from the last VisibilityRun's completed_at, the same
    on-demand-computation philosophy already used for metrics themselves.
    Skips a store with no active VisibilityQuestion rows yet (nothing to
    measure) and a store with a run still in flight (never double-dispatch)."""
    now = utcnow()
    active_stores = session.exec(select(Store).where(Store.status == StoreStatus.active)).all()

    due: list[uuid.UUID] = []
    for store in active_stores:
        has_questions = session.exec(
            select(VisibilityQuestion.id).where(VisibilityQuestion.store_id == store.id, VisibilityQuestion.is_active == True)  # noqa: E712
        ).first()
        if has_questions is None:
            continue

        latest = session.exec(
            select(VisibilityRun).where(VisibilityRun.store_id == store.id).order_by(VisibilityRun.started_at.desc())  # type: ignore[union-attr]
        ).first()
        if latest is not None and latest.status == "running":
            continue
        if latest is None or (latest.completed_at is not None and now - latest.completed_at >= timedelta(days=VISIBILITY_RUN_INTERVAL_DAYS)):
            due.append(store.id)

    return due
