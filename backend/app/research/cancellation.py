import uuid

from sqlmodel import Session, select, update

from app.models.base import utcnow
from app.models.research import ResearchRun, RunStatus

# Part H8 — the exact stop_reason string the iterative loop uses when it
# stops because of an explicit cancellation request, so
# ResearchOrchestrator.execute_run can tell "cancelled" apart from every
# other stop reason (budget/duration/empty-queue/low-new-information-rate)
# after the loop returns, and mark the run's final status accordingly.
CANCELLATION_STOP_REASON = "cancelled by request"


def request_run_cancellation(session: Session, research_run_id: uuid.UUID) -> bool:
    """Atomic, idempotent: only a run still in pending/running can be
    cancelled, and only the first caller's request actually takes effect
    (mirrors the same UPDATE...WHERE claim pattern execute_run itself uses
    for its own idempotency, Part H7). Returns True if this call is the one
    that set the flag, False if the run was already completed/failed/
    cancelled, or already had a cancellation pending."""
    result = session.execute(
        update(ResearchRun)
        .where(ResearchRun.id == research_run_id)
        .where(ResearchRun.status.in_([RunStatus.pending, RunStatus.running]))  # type: ignore[attr-defined]
        .where(ResearchRun.cancel_requested_at.is_(None))  # type: ignore[union-attr]
        .values(cancel_requested_at=utcnow())
    )
    session.commit()
    return result.rowcount > 0


def is_cancellation_requested(session: Session, research_run_id: uuid.UUID) -> bool:
    """Cheap scalar read the iterative loop polls once per batch — never
    trusts an in-memory ResearchRun object, since another process/session
    may have requested cancellation after this run's row was last loaded."""
    cancel_requested_at = session.exec(
        select(ResearchRun.cancel_requested_at).where(ResearchRun.id == research_run_id)
    ).first()
    return cancel_requested_at is not None
