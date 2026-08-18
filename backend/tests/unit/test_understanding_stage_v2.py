"""Phase 7 (scenario group: stage transitions) — the new 7-value stage
machine (resolving_identity/provisional/catalog_scanning/ready/
needs_confirmation/catalog_blocked/failed), only entered once a real
identity_run is passed. test_store_classification_gate.py's 8 tests (the
legacy 5-value machine) are the backward-compatibility contract for this
extension and must keep passing unmodified — verified separately, not
duplicated here."""

import uuid

from app.models.research import AgentRun, RunStatus
from app.store_intelligence.understanding import (
    MIN_IDENTITY_CONFIDENCE_FOR_PROVISIONAL,
    resolve_understanding_stage,
)


def _agent_run(status: RunStatus) -> AgentRun:
    return AgentRun(research_run_id=uuid.uuid4(), agent_type="x", status=status)


def _stage(*, crawl=None, identity=RunStatus.completed, confidence=0.9, brand="Example", catalog="pending"):
    return resolve_understanding_stage(
        crawl_run=_agent_run(crawl) if crawl is not None else None,
        classification_run=None,
        classification_confidence=None,
        classification_skipped=False,
        identity_run=_agent_run(identity),
        identity_confidence=confidence,
        identity_brand_name=brand,
        catalog_status=catalog,
    )


def test_resolving_identity_when_identity_still_running():
    assert _stage(crawl=RunStatus.completed, identity=RunStatus.running) == "resolving_identity"


def test_resolving_identity_when_no_crawl_run_yet_even_if_identity_run_exists():
    assert _stage(crawl=None, identity=RunStatus.completed) == "resolving_identity"


def test_failed_when_crawl_failed_and_identity_never_completed():
    assert _stage(crawl=RunStatus.failed, identity=RunStatus.failed) == "failed"


def test_needs_confirmation_when_identity_completed_below_confidence_bar():
    assert (
        _stage(crawl=RunStatus.completed, identity=RunStatus.completed, confidence=MIN_IDENTITY_CONFIDENCE_FOR_PROVISIONAL - 0.01)
        == "needs_confirmation"
    )


def test_needs_confirmation_when_identity_completed_without_a_brand_name():
    assert _stage(crawl=RunStatus.completed, identity=RunStatus.completed, confidence=0.9, brand=None) == "needs_confirmation"


def test_needs_confirmation_never_a_hard_wall_unlike_legacy_low_confidence():
    """The whole point of Phase 2: a plausible-but-unconfirmed identity
    still lets registration continue — never the old low_confidence wall."""
    stage = _stage(crawl=RunStatus.completed, identity=RunStatus.completed, confidence=0.1)
    assert stage == "needs_confirmation"
    assert stage != "low_confidence"
    assert stage != "failed"


def test_resolving_identity_when_identity_failed_and_legacy_path_would_say_pending():
    """identity_run itself failed/skipped (not completed) and crawl hasn't
    finished either — falls back to the legacy pending, translated onto the
    new vocabulary."""
    assert _stage(crawl=RunStatus.running, identity=RunStatus.failed, confidence=None, brand=None) == "resolving_identity"


def test_catalog_scanning_when_identity_failed_and_legacy_path_would_say_partial():
    """identity resolution itself failed, but crawl succeeded and
    classification hasn't finished — legacy 'partial' maps onto the new
    'catalog_scanning' (crawl-derived classification is still enrichment
    happening in the background either way)."""
    assert _stage(crawl=RunStatus.completed, identity=RunStatus.failed, confidence=None, brand=None) == "catalog_scanning"


def test_provisional_when_identity_resolved_and_catalog_still_pending():
    """Zero products/empty catalog so far — identity alone is enough to
    reach provisional, never blocked on the catalog scan."""
    assert _stage(crawl=RunStatus.completed, identity=RunStatus.completed, catalog="pending") == "provisional"


def test_catalog_scanning_when_identity_resolved_and_catalog_actively_scanning():
    assert _stage(crawl=RunStatus.completed, identity=RunStatus.completed, catalog="scanning") == "catalog_scanning"


def test_ready_when_identity_resolved_and_catalog_ready():
    assert _stage(crawl=RunStatus.completed, identity=RunStatus.completed, catalog="ready") == "ready"


def test_ready_when_identity_resolved_and_catalog_partial():
    assert _stage(crawl=RunStatus.completed, identity=RunStatus.completed, catalog="partial") == "ready"


def test_catalog_blocked_when_identity_resolved_and_catalog_blocked():
    assert _stage(crawl=RunStatus.completed, identity=RunStatus.completed, catalog="blocked") == "catalog_blocked"


def test_catalog_blocked_when_identity_resolved_and_catalog_scan_itself_failed():
    assert _stage(crawl=RunStatus.completed, identity=RunStatus.completed, catalog="failed") == "catalog_blocked"


def test_legacy_five_value_machine_untouched_when_no_identity_run_passed():
    """identity_run=None (the default) must reproduce the exact pre-Phase-2
    behavior — this is the backward-compatibility contract itself."""
    assert resolve_understanding_stage(
        crawl_run=_agent_run(RunStatus.completed), classification_run=_agent_run(RunStatus.completed),
        classification_confidence=0.9, classification_skipped=False,
    ) == "ready"


def test_ready_when_identity_was_skipped_but_classification_succeeded_confidently():
    """Real bug caught live on modernsupply.com.sa: web_search identity
    resolution failed/was unavailable (identity_run.status is still
    'completed' — a skip is a normal, non-exceptional outcome — but
    identity_confidence/brand_name are both None), while crawl+
    classification succeeded on their own with a confident, real result
    (0.85 confidence, real categories/products). Before this fix, a skip
    was indistinguishable from 'genuinely tried and landed low-confidence,'
    so every web_search-unavailable store got stuck at needs_confirmation
    with a blank display_name even when the crawl path alone already had
    everything needed to call it ready."""
    stage = resolve_understanding_stage(
        crawl_run=_agent_run(RunStatus.completed), classification_run=_agent_run(RunStatus.completed),
        classification_confidence=0.85, classification_skipped=False,
        identity_run=_agent_run(RunStatus.completed), identity_confidence=None, identity_brand_name=None,
        identity_skipped=True, catalog_status="partial",
    )
    assert stage == "ready"


def test_needs_confirmation_still_wins_when_identity_genuinely_landed_low_confidence():
    """The fix must not swallow the real needs_confirmation case — only a
    genuine skip (identity_skipped=True) reroutes to the legacy fallback;
    a real, non-skipped low-confidence identity result still means
    needs_confirmation exactly as before."""
    stage = resolve_understanding_stage(
        crawl_run=_agent_run(RunStatus.completed), classification_run=_agent_run(RunStatus.completed),
        classification_confidence=0.85, classification_skipped=False,
        identity_run=_agent_run(RunStatus.completed), identity_confidence=0.1, identity_brand_name=None,
        identity_skipped=False, catalog_status="partial",
    )
    assert stage == "needs_confirmation"


def test_needs_confirmation_when_identity_skipped_and_classification_also_weak():
    """A skip doesn't fabricate confidence out of nowhere — if the legacy
    crawl+classification path itself would only reach low_confidence/ready-
    without-a-name, the skip fallback still lands on needs_confirmation
    (mapped from the legacy 'low_confidence'/'ready' outcomes, per the
    existing fallback mapping), never silently promoted to ready."""
    stage = resolve_understanding_stage(
        crawl_run=_agent_run(RunStatus.completed), classification_run=_agent_run(RunStatus.completed),
        classification_confidence=0.1, classification_skipped=False,
        identity_run=_agent_run(RunStatus.completed), identity_confidence=None, identity_brand_name=None,
        identity_skipped=True, catalog_status="partial",
    )
    assert stage == "needs_confirmation"
