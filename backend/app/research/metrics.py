import uuid
from dataclasses import dataclass

from sqlmodel import Session, func, select

from app.models.ai_execution import AIExecution
from app.models.competitor import Competitor
from app.models.evidence import Evidence
from app.models.finding import Finding, FindingStatus
from app.models.intent import Intent, IntentSource
from app.models.observation import PageObservation
from app.models.page_intelligence import PageGapAnalysis
from app.models.research_task import ResearchTask
from app.models.serp import SerpExecution


@dataclass
class ResearchMetrics:
    total_tasks: int
    search_queries_executed: int
    ai_conversations_executed: int
    pages_crawled: int
    competitor_pages_analyzed: int
    competitors_discovered: int
    intents_discovered: int
    new_queries_discovered: int
    findings_generated: int
    findings_validated: int
    evidence_records: int
    total_tokens: int
    total_cost_usd: float
    duration_seconds: float
    research_depth_reached: int
    stop_reason: str = ""
    # Part H — concurrency/performance visibility, derived from each
    # research_task's own [started_at, completed_at] window (an
    # interval-overlap sweep), not tracked live by the loop itself.
    peak_concurrency: int = 0
    average_concurrency: float = 0.0
    sequential_time_estimate_seconds: float = 0.0
    actual_parallel_duration_seconds: float = 0.0


def _compute_concurrency_stats(tasks: list[ResearchTask], wall_clock_seconds: float) -> tuple[int, float, float]:
    """Returns (peak_concurrency, average_concurrency, sequential_time_estimate_seconds).
    average_concurrency = total task-seconds / wall-clock seconds — the
    standard 'average number of tasks in flight' utilization metric.
    sequential_time_estimate_seconds = sum of every task's own duration, as
    if they had run one after another — paired with the run's real
    wall-clock duration this shows the actual speedup from concurrency."""
    intervals = [(t.started_at, t.completed_at) for t in tasks if t.started_at and t.completed_at]
    if not intervals:
        return 0, 0.0, 0.0

    total_task_seconds = sum((end - start).total_seconds() for start, end in intervals)
    events = sorted(
        [(start, 1) for start, _ in intervals] + [(end, -1) for _, end in intervals],
        key=lambda e: (e[0], -e[1]),  # starts before ends at an identical timestamp, so touching intervals still count as overlapping
    )
    current = 0
    peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)

    average = (total_task_seconds / wall_clock_seconds) if wall_clock_seconds > 0 else 0.0
    return peak, average, total_task_seconds


def compute_research_metrics(
    session: Session, research_run_id: uuid.UUID, *, duration_seconds: float, stop_reason: str = ""
) -> ResearchMetrics:
    """End-of-run report (Group D2 spec section 13) — covers the whole
    research_run (fixed pipeline phases + the iterative loop), not just the
    loop portion, since the user needs one number per dimension for unit
    economics."""
    tasks = session.exec(select(ResearchTask).where(ResearchTask.research_run_id == research_run_id)).all()
    ai_executions = session.exec(select(AIExecution).where(AIExecution.research_run_id == research_run_id)).all()
    serp_executions = session.exec(select(SerpExecution).where(SerpExecution.research_run_id == research_run_id)).all()
    findings = session.exec(select(Finding).where(Finding.research_run_id == research_run_id)).all()
    intents = session.exec(select(Intent).where(Intent.research_run_id == research_run_id)).all()

    pages_crawled = session.exec(
        select(func.count()).select_from(PageObservation).where(PageObservation.research_run_id == research_run_id)
    ).one()
    competitor_pages_analyzed = session.exec(
        select(func.count()).select_from(PageGapAnalysis).where(PageGapAnalysis.research_run_id == research_run_id)
    ).one()
    competitors_discovered = session.exec(
        select(func.count()).select_from(Competitor).where(Competitor.first_seen_research_run_id == research_run_id)
    ).one()
    evidence_records = session.exec(
        select(func.count()).select_from(Evidence).where(Evidence.research_run_id == research_run_id)
    ).one()

    peak_concurrency, average_concurrency, sequential_time_estimate = _compute_concurrency_stats(
        tasks, duration_seconds
    )

    return ResearchMetrics(
        total_tasks=len(tasks),
        search_queries_executed=len(serp_executions),
        ai_conversations_executed=len(ai_executions),
        pages_crawled=pages_crawled,
        competitor_pages_analyzed=competitor_pages_analyzed,
        competitors_discovered=competitors_discovered,
        intents_discovered=len(intents),
        new_queries_discovered=sum(1 for i in intents if i.source == IntentSource.ai_expansion),
        findings_generated=len(findings),
        findings_validated=sum(1 for f in findings if f.status == FindingStatus.validated),
        evidence_records=evidence_records,
        total_tokens=sum((e.input_tokens or 0) + (e.output_tokens or 0) for e in ai_executions),
        total_cost_usd=sum(e.cost_usd or 0.0 for e in ai_executions) + sum(e.cost_usd or 0.0 for e in serp_executions),
        duration_seconds=duration_seconds,
        research_depth_reached=max((t.depth for t in tasks), default=0),
        stop_reason=stop_reason,
        peak_concurrency=peak_concurrency,
        average_concurrency=average_concurrency,
        sequential_time_estimate_seconds=sequential_time_estimate,
        actual_parallel_duration_seconds=duration_seconds,
    )
