import uuid
from sqlalchemy import inspect
from sqlmodel import Session, select

from app.models.analysis_snapshot import AnalysisComponentSnapshot
from app.models.base import utcnow

VALID_STATUSES = {"not_started", "queued", "running", "partial", "completed", "failed", "stale"}


def _snapshot_table_available(session: Session) -> bool:
    """Keep fast snapshots optional for databases created before this feature.

    Snapshot persistence improves progressive reporting, but it must never
    prevent the underlying analysis from starting.
    """
    return inspect(session.get_bind()).has_table(AnalysisComponentSnapshot.__tablename__)


def update_component_snapshot(
    session: Session,
    *,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    component: str,
    status: str,
    progress_completed: int = 0,
    progress_total: int = 0,
    payload: dict | None = None,
    error: str | None = None,
) -> AnalysisComponentSnapshot:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid component snapshot status: {status}")
    if not _snapshot_table_available(session):
        return AnalysisComponentSnapshot(
            store_id=store_id,
            research_run_id=research_run_id,
            component=component,
            status=status,
            progress_completed=progress_completed,
            progress_total=progress_total,
            payload=payload or {},
            error=error,
            started_at=utcnow() if status == "running" else None,
            completed_at=utcnow() if status in {"completed", "failed"} else None,
        )
    row = session.exec(
        select(AnalysisComponentSnapshot)
        .where(AnalysisComponentSnapshot.research_run_id == research_run_id)
        .where(AnalysisComponentSnapshot.component == component)
    ).first()
    now = utcnow()
    if row is None:
        row = AnalysisComponentSnapshot(
            store_id=store_id,
            research_run_id=research_run_id,
            component=component,
            status=status,
        )
    if status == "running" and row.started_at is None:
        row.started_at = now
    if status in {"completed", "failed"}:
        row.completed_at = now
    row.status = status
    row.progress_completed = progress_completed
    row.progress_total = progress_total
    row.payload = payload if payload is not None else row.payload
    row.error = error
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def latest_component_snapshots(session: Session, store_id: uuid.UUID) -> dict[str, AnalysisComponentSnapshot]:
    if not _snapshot_table_available(session):
        return {}
    rows = session.exec(
        select(AnalysisComponentSnapshot)
        .where(AnalysisComponentSnapshot.store_id == store_id)
        .order_by(AnalysisComponentSnapshot.created_at.desc())  # type: ignore[arg-type]
    ).all()
    latest: dict[str, AnalysisComponentSnapshot] = {}
    latest_completed: dict[str, AnalysisComponentSnapshot] = {}
    for row in rows:
        latest.setdefault(row.component, row)
        if row.status == "completed":
            latest_completed.setdefault(row.component, row)
    # Never replace a valid published result with a queued/running/failed refresh.
    return {component: latest_completed.get(component, row) for component, row in latest.items()}
