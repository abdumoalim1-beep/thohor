"""Part R7 (Round 1 remediation) — get_session() (app.core.db, the real
DATABASE_URL-backed engine) must refuse to run while pytest is active unless
explicitly overridden. Every real test already uses the isolated `session`
fixture or a FastAPI dependency_overrides swap, so this guard should never
fire in practice — it exists purely to fail loudly if a future test forgets
to override the dependency, instead of silently touching the real database."""

import os

import pytest

from app.core.db import get_session


def test_get_session_raises_under_pytest_without_explicit_override():
    # PYTEST_CURRENT_TEST is always set by pytest itself while a test runs —
    # this assertion is really just documenting that fact for the reader.
    assert os.environ.get("PYTEST_CURRENT_TEST")
    assert os.environ.get("MERSAD_ALLOW_TEST_DB_ACCESS") is None

    with pytest.raises(RuntimeError, match="real DATABASE_URL-backed engine"):
        next(get_session())


def test_get_session_allows_explicit_opt_out(monkeypatch):
    """Proves the opt-out env var lets execution past the guard — without
    ever opening a real database connection (this dev environment does have
    a real reachable Postgres, so a naive 'just call get_session()' test
    here would itself be exactly the real-DB-touching mistake this guard
    exists to prevent)."""
    monkeypatch.setenv("MERSAD_ALLOW_TEST_DB_ACCESS", "1")
    sentinel = object()

    class _FakeSessionContextManager:
        def __enter__(self):
            return sentinel

        def __exit__(self, *exc_info):
            return False

    monkeypatch.setattr("app.core.db.Session", lambda _engine: _FakeSessionContextManager())

    gen = get_session()
    try:
        assert next(gen) is sentinel
    finally:
        gen.close()
