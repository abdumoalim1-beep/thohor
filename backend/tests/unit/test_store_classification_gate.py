import uuid

from app.crawler.store_intelligence import (
    MIN_OBSERVATIONS_FOR_CLASSIFICATION,
    has_sufficient_observations_for_classification,
)
from app.models.research import AgentRun, RunStatus
from app.store_intelligence.understanding import (
    MIN_CLASSIFICATION_CONFIDENCE_FOR_READY,
    resolve_understanding_stage,
)


def test_has_sufficient_observations_boundary():
    assert has_sufficient_observations_for_classification([]) is False
    assert has_sufficient_observations_for_classification([object()] * (MIN_OBSERVATIONS_FOR_CLASSIFICATION - 1)) is False
    assert has_sufficient_observations_for_classification([object()] * MIN_OBSERVATIONS_FOR_CLASSIFICATION) is True
    assert has_sufficient_observations_for_classification([object()] * (MIN_OBSERVATIONS_FOR_CLASSIFICATION + 5)) is True


def _agent_run(status: RunStatus) -> AgentRun:
    return AgentRun(research_run_id=uuid.uuid4(), agent_type="x", status=status)


def test_resolve_understanding_stage_pending_when_no_crawl_run_yet():
    assert resolve_understanding_stage(
        crawl_run=None, classification_run=None, classification_confidence=None, classification_skipped=False
    ) == "pending"


def test_resolve_understanding_stage_pending_while_crawl_still_running():
    assert resolve_understanding_stage(
        crawl_run=_agent_run(RunStatus.running), classification_run=None,
        classification_confidence=None, classification_skipped=False,
    ) == "pending"


def test_resolve_understanding_stage_failed_when_crawl_failed():
    assert resolve_understanding_stage(
        crawl_run=_agent_run(RunStatus.failed), classification_run=None,
        classification_confidence=None, classification_skipped=False,
    ) == "failed"


def test_resolve_understanding_stage_partial_while_classification_still_running():
    assert resolve_understanding_stage(
        crawl_run=_agent_run(RunStatus.completed), classification_run=_agent_run(RunStatus.running),
        classification_confidence=None, classification_skipped=False,
    ) == "partial"


def test_resolve_understanding_stage_low_confidence_when_classification_was_skipped():
    """Skipped means the crawl found too little to even attempt
    classification — must never be shown as "ready"."""
    assert resolve_understanding_stage(
        crawl_run=_agent_run(RunStatus.completed), classification_run=_agent_run(RunStatus.completed),
        classification_confidence=None, classification_skipped=True,
    ) == "low_confidence"


def test_resolve_understanding_stage_low_confidence_when_below_threshold():
    assert resolve_understanding_stage(
        crawl_run=_agent_run(RunStatus.completed), classification_run=_agent_run(RunStatus.completed),
        classification_confidence=MIN_CLASSIFICATION_CONFIDENCE_FOR_READY - 0.01, classification_skipped=False,
    ) == "low_confidence"


def test_resolve_understanding_stage_ready_when_confident():
    assert resolve_understanding_stage(
        crawl_run=_agent_run(RunStatus.completed), classification_run=_agent_run(RunStatus.completed),
        classification_confidence=MIN_CLASSIFICATION_CONFIDENCE_FOR_READY, classification_skipped=False,
    ) == "ready"


def test_resolve_understanding_stage_ready_when_classification_run_failed_but_crawl_succeeded():
    """A classification failure (LLM error, not a data-completeness skip)
    still counts as "the pipeline reached a terminal state" — matches the
    pre-existing behavior this function replaces."""
    assert resolve_understanding_stage(
        crawl_run=_agent_run(RunStatus.completed), classification_run=_agent_run(RunStatus.failed),
        classification_confidence=None, classification_skipped=False,
    ) == "ready"
