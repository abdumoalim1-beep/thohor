import itertools
from datetime import timedelta

from app.core.cadence import compute_next_scheduled_run_at
from app.models.base import utcnow
from app.models.org import Organization
from app.models.store import Store, StoreStatus
from app.workers.scheduling import dispatch_due_stores

_slug_counter = itertools.count()


def test_compute_next_scheduled_run_at_daily():
    now = utcnow()
    result = compute_next_scheduled_run_at("daily", now)
    assert result == now + timedelta(days=1)


def test_compute_next_scheduled_run_at_manual_returns_none():
    assert compute_next_scheduled_run_at("manual", utcnow()) is None


def test_compute_next_scheduled_run_at_unknown_cadence_returns_none():
    assert compute_next_scheduled_run_at("bogus", utcnow()) is None


def _make_store(session, *, cadence, next_run_at, status=StoreStatus.active):
    org = Organization(name="t", slug=f"t-sched-{next(_slug_counter)}")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(
        organization_id=org.id, url="https://store.example", status=status,
        monitoring_cadence=cadence, next_scheduled_run_at=next_run_at,
    )
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


def test_dispatch_due_stores_dispatches_only_due_active_stores(session):
    now = utcnow()
    due = _make_store(session, cadence="daily", next_run_at=now - timedelta(hours=1))
    not_due_yet = _make_store(session, cadence="weekly", next_run_at=now + timedelta(days=3))
    never_scheduled = _make_store(session, cadence="manual", next_run_at=None)
    pending_store = _make_store(session, cadence="daily", next_run_at=now - timedelta(hours=1), status=StoreStatus.pending)

    dispatched = dispatch_due_stores(session)
    dispatched_store_ids = {store_id for store_id, _ in dispatched}

    assert due.id in dispatched_store_ids
    assert not_due_yet.id not in dispatched_store_ids
    assert never_scheduled.id not in dispatched_store_ids
    assert pending_store.id not in dispatched_store_ids


def test_dispatch_due_stores_advances_schedule_and_creates_pending_run(session):
    now = utcnow()
    store = _make_store(session, cadence="weekly", next_run_at=now - timedelta(minutes=5))

    dispatched = dispatch_due_stores(session)
    assert len(dispatched) == 1
    _, run_id = dispatched[0]

    session.refresh(store)
    assert store.next_scheduled_run_at is not None
    # SQLite round-trips DateTime as naive regardless of what was written;
    # strip tzinfo on both sides for the comparison (a real Postgres column
    # wouldn't need this — this is a test-storage quirk, not app behavior).
    assert store.next_scheduled_run_at.replace(tzinfo=None) > now.replace(tzinfo=None)

    from app.models.research import ResearchRun, ResearchRunType, RunStatus

    run = session.get(ResearchRun, run_id)
    assert run is not None
    assert run.run_type == ResearchRunType.monitoring
    assert run.status == RunStatus.pending
