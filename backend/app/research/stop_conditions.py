from app.research.budget import ResearchBudget
from app.research.cancellation import CANCELLATION_STOP_REASON

NEW_INFORMATION_RATE_WINDOW = 5
NEW_INFORMATION_RATE_FLOOR = 0.2


def should_stop_research(
    *,
    budget: ResearchBudget,
    elapsed_seconds: float,
    pending_task_count: int,
    recent_new_entity_counts: list[int],
    cancellation_requested: bool = False,
) -> tuple[bool, str]:
    """Stop conditions beyond 'the queue is empty' (Group D2 spec section
    11). max_depth isn't checked here — it's enforced upstream, at the
    moment a child task would be created (depth = parent.depth + 1 >
    max_depth means the task is never queued in the first place), so an
    exhausted depth naturally drains toward 'no pending tasks remaining'
    below rather than needing a separate check.

    Part H8 — cancellation is checked first: once requested, it must win
    over every other reason (even a run that happens to also be at its
    budget limit) so the loop's stop_reason is always unambiguous.
    """
    if cancellation_requested:
        return True, CANCELLATION_STOP_REASON

    exhausted = budget.exhausted_dimensions()
    if exhausted:
        return True, f"budget exhausted: {', '.join(exhausted)}"

    if elapsed_seconds >= budget.max_duration_seconds:
        return True, "max_duration_seconds reached"

    if pending_task_count == 0:
        return True, "no pending tasks remaining"

    if len(recent_new_entity_counts) >= NEW_INFORMATION_RATE_WINDOW:
        window = recent_new_entity_counts[-NEW_INFORMATION_RATE_WINDOW:]
        rate = sum(window) / len(window)
        if rate < NEW_INFORMATION_RATE_FLOOR:
            return True, f"new information rate too low ({rate:.2f} < {NEW_INFORMATION_RATE_FLOOR})"

    return False, ""
