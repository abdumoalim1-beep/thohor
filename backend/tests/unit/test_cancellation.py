"""Part H8 — request_run_cancellation / is_cancellation_requested."""

from app.models.org import Organization
from app.models.research import ResearchRun, RunStatus
from app.models.store import Store
from app.research.cancellation import is_cancellation_requested, request_run_cancellation


def _make_run(session, status: RunStatus = RunStatus.running) -> ResearchRun:
    org = Organization(name="t", slug=f"t-cancel-{status.value}")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id, status=status)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def test_request_run_cancellation_succeeds_on_a_running_run(session):
    run = _make_run(session, RunStatus.running)

    accepted = request_run_cancellation(session, run.id)

    assert accepted is True
    session.refresh(run)
    assert run.cancel_requested_at is not None
    assert is_cancellation_requested(session, run.id) is True


def test_request_run_cancellation_succeeds_on_a_pending_run(session):
    run = _make_run(session, RunStatus.pending)

    assert request_run_cancellation(session, run.id) is True


def test_request_run_cancellation_is_idempotent(session):
    """A second request against an already-cancellation-requested run must
    not error and must not re-stamp cancel_requested_at (rowcount == 0)."""
    run = _make_run(session, RunStatus.running)
    assert request_run_cancellation(session, run.id) is True
    session.refresh(run)
    first_timestamp = run.cancel_requested_at

    second = request_run_cancellation(session, run.id)

    assert second is False
    session.refresh(run)
    assert run.cancel_requested_at == first_timestamp


def test_request_run_cancellation_rejects_a_completed_run(session):
    run = _make_run(session, RunStatus.completed)

    accepted = request_run_cancellation(session, run.id)

    assert accepted is False
    assert is_cancellation_requested(session, run.id) is False


def test_request_run_cancellation_rejects_a_failed_run(session):
    run = _make_run(session, RunStatus.failed)

    assert request_run_cancellation(session, run.id) is False


def test_is_cancellation_requested_defaults_to_false(session):
    run = _make_run(session, RunStatus.running)

    assert is_cancellation_requested(session, run.id) is False
