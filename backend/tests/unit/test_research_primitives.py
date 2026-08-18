import uuid

from app.core.config import Settings
from app.models.research_task import TaskType
from app.research.budget import ResearchBudget
from app.research.fingerprint import compute_task_fingerprint
from app.research.stop_conditions import should_stop_research


def _budget(**overrides) -> ResearchBudget:
    defaults = dict(
        max_search_requests=10,
        max_ai_requests=10,
        max_pages=10,
        max_tokens=10_000,
        max_cost_usd=1.0,
        max_duration_seconds=60.0,
        max_depth=3,
        max_tasks=10,
    )
    defaults.update(overrides)
    return ResearchBudget(**defaults)


def test_fingerprint_is_deterministic_for_same_inputs():
    run_id = uuid.uuid4()
    fp1 = compute_task_fingerprint(TaskType.competitor_deep_dive, "  Rival.Test  ", "ar", run_id)
    fp2 = compute_task_fingerprint(TaskType.competitor_deep_dive, "rival.test", "ar", run_id)
    assert fp1 == fp2


def test_fingerprint_differs_for_different_task_type_or_target():
    run_id = uuid.uuid4()
    base = compute_task_fingerprint(TaskType.competitor_deep_dive, "rival.test", "ar", run_id)
    other_type = compute_task_fingerprint(TaskType.page_compare, "rival.test", "ar", run_id)
    other_target = compute_task_fingerprint(TaskType.competitor_deep_dive, "other.test", "ar", run_id)
    other_run = compute_task_fingerprint(TaskType.competitor_deep_dive, "rival.test", "ar", uuid.uuid4())
    assert len({base, other_type, other_target, other_run}) == 4


def test_research_budget_from_settings_reads_configured_fields():
    settings = Settings(
        research_max_search_requests=5,
        research_max_ai_requests=7,
        research_max_pages=3,
        research_max_tokens=1000,
        research_max_cost_usd=0.5,
        research_max_duration_seconds=30.0,
        research_max_depth=2,
        research_max_tasks=9,
    )
    budget = ResearchBudget.from_settings(settings)
    assert budget.max_search_requests == 5
    assert budget.max_tasks == 9
    assert budget.has_capacity()


def test_budget_exhausted_dimensions_reports_each_cap_independently():
    budget = _budget(max_cost_usd=0.1, max_search_requests=1)
    budget.record_task(cost_usd=0.15, search_requests=1)
    exhausted = budget.exhausted_dimensions()
    assert "cost_usd" in exhausted
    assert "search_requests" in exhausted
    assert not budget.has_capacity()


def test_budget_record_task_accumulates_and_increments_tasks_used():
    budget = _budget()
    budget.record_task(search_requests=2, ai_requests=1, pages=1, tokens=500, cost_usd=0.1)
    budget.record_task(ai_requests=3, tokens=200)
    assert budget.search_requests_used == 2
    assert budget.ai_requests_used == 4
    assert budget.pages_used == 1
    assert budget.tokens_used == 700
    assert budget.cost_usd_used == 0.1
    assert budget.tasks_used == 2


def test_should_stop_when_budget_exhausted():
    budget = _budget(max_tasks=1)
    budget.record_task()
    stop, reason = should_stop_research(
        budget=budget, elapsed_seconds=1.0, pending_task_count=5, recent_new_entity_counts=[]
    )
    assert stop is True
    assert "budget exhausted" in reason


def test_should_stop_when_cancellation_requested():
    """Part H8 — cancellation wins even when nothing else would stop the
    run yet (healthy budget, tasks pending, good new-information rate)."""
    budget = _budget()
    stop, reason = should_stop_research(
        budget=budget,
        elapsed_seconds=1.0,
        pending_task_count=5,
        recent_new_entity_counts=[2, 3, 1, 4, 2],
        cancellation_requested=True,
    )
    assert stop is True
    assert reason == "cancelled by request"


def test_should_stop_when_duration_exceeded():
    budget = _budget()
    stop, reason = should_stop_research(
        budget=budget, elapsed_seconds=999.0, pending_task_count=5, recent_new_entity_counts=[]
    )
    assert stop is True
    assert "duration" in reason


def test_should_stop_when_queue_empty():
    budget = _budget()
    stop, reason = should_stop_research(
        budget=budget, elapsed_seconds=1.0, pending_task_count=0, recent_new_entity_counts=[]
    )
    assert stop is True
    assert "no pending tasks" in reason


def test_should_stop_when_new_information_rate_too_low():
    budget = _budget()
    stop, reason = should_stop_research(
        budget=budget,
        elapsed_seconds=1.0,
        pending_task_count=5,
        recent_new_entity_counts=[0, 0, 0, 0, 0],
    )
    assert stop is True
    assert "information rate" in reason


def test_should_not_stop_when_everything_healthy():
    budget = _budget()
    stop, reason = should_stop_research(
        budget=budget,
        elapsed_seconds=1.0,
        pending_task_count=3,
        recent_new_entity_counts=[2, 3, 1, 4, 2],
    )
    assert stop is False
    assert reason == ""
