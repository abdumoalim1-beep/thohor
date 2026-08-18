import os
from collections.abc import Iterator

from sqlmodel import Session, create_engine

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, echo=False)


def get_session() -> Iterator[Session]:
    """Part R7 (Round 1 remediation) — every pytest test in this project
    already uses an isolated in-memory sqlite session (tests/conftest.py's
    `session` fixture, or a per-test FastAPI `dependency_overrides[get_session]`
    override); this real, DATABASE_URL-backed engine should never actually
    execute a query while pytest is running. That invariant held by
    convention only — nothing enforced it, and Round 1's remediation traced
    a real, separate contamination incident (a discarded dry-run research
    run against the real dev database — see app.core.domain.is_synthetic_test_domain)
    caused by exactly this class of test-data-meets-real-database mistake.
    `PYTEST_CURRENT_TEST` is set by pytest itself for the duration of every
    test; a future test that forgets to override this dependency now fails
    loudly instead of silently reading or writing the real database."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("MERSAD_ALLOW_TEST_DB_ACCESS"):
        raise RuntimeError(
            "get_session() (the real DATABASE_URL-backed engine) was called while running "
            "under pytest. Tests must use the isolated `session` fixture (tests/conftest.py) "
            "or override get_session via FastAPI dependency_overrides — never the real "
            "database. If this is a deliberate manual/integration test against a real "
            "database, set MERSAD_ALLOW_TEST_DB_ACCESS=1 explicitly."
        )
    with Session(engine) as session:
        yield session
