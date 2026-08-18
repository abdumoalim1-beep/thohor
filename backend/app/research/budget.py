from dataclasses import dataclass, field

from app.core.config import Settings


@dataclass
class ResearchBudget:
    """Live consumption tracker for one research_run's iterative loop.
    Every dimension the user asked for (Group D2 spec section 10) is a hard
    ceiling — the loop stops the instant any one is reached, not just when
    the task queue empties (see app/research/stop_conditions.py)."""

    max_search_requests: int
    max_ai_requests: int
    max_pages: int
    max_tokens: int
    max_cost_usd: float
    max_duration_seconds: float
    max_depth: int
    max_tasks: int

    search_requests_used: int = field(default=0)
    ai_requests_used: int = field(default=0)
    pages_used: int = field(default=0)
    tokens_used: int = field(default=0)
    cost_usd_used: float = field(default=0.0)
    tasks_used: int = field(default=0)

    @classmethod
    def from_settings(cls, settings: Settings) -> "ResearchBudget":
        return cls(
            max_search_requests=settings.research_max_search_requests,
            max_ai_requests=settings.research_max_ai_requests,
            max_pages=settings.research_max_pages,
            max_tokens=settings.research_max_tokens,
            max_cost_usd=settings.research_max_cost_usd,
            max_duration_seconds=settings.research_max_duration_seconds,
            max_depth=settings.research_max_depth,
            max_tasks=settings.research_max_tasks,
        )

    def exhausted_dimensions(self) -> list[str]:
        """Names of every dimension currently at or past its cap — empty
        list means the loop may keep going (as far as budget is concerned;
        duration/depth/information-rate are checked separately)."""
        exhausted = []
        if self.search_requests_used >= self.max_search_requests:
            exhausted.append("search_requests")
        if self.ai_requests_used >= self.max_ai_requests:
            exhausted.append("ai_requests")
        if self.pages_used >= self.max_pages:
            exhausted.append("pages")
        if self.tokens_used >= self.max_tokens:
            exhausted.append("tokens")
        if self.cost_usd_used >= self.max_cost_usd:
            exhausted.append("cost_usd")
        if self.tasks_used >= self.max_tasks:
            exhausted.append("tasks")
        return exhausted

    def has_capacity(self) -> bool:
        return not self.exhausted_dimensions()

    def record_task(
        self,
        *,
        search_requests: int = 0,
        ai_requests: int = 0,
        pages: int = 0,
        tokens: int = 0,
        cost_usd: float = 0.0,
        tasks_completed: int = 1,
    ) -> None:
        """Part H4 — `tasks_completed` lets one call record a whole
        concurrent batch's aggregate usage at once (tasks_completed = how
        many of that batch actually succeeded), instead of requiring one
        call per task. The aggregate numbers stay exactly correct under
        concurrency even though individual tasks' own `cost` becomes an
        even-split approximation (see app/research/loop.py) — this is what
        actually gates the loop, and it never loses precision."""
        self.search_requests_used += search_requests
        self.ai_requests_used += ai_requests
        self.pages_used += pages
        self.tokens_used += tokens
        self.cost_usd_used += cost_usd
        self.tasks_used += tasks_completed
