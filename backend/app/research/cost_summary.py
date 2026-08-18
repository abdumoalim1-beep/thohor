import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.ai_visibility.surfaces import AI_VISIBILITY_SURFACES
from app.models.ai_execution import AIExecution
from app.models.serp import SerpExecution

AI_VISIBILITY_TASK_TYPE = "ai_visibility_probe"
_SURFACE_BY_PROVIDER_MODEL = {(s.provider, s.model): s.surface for s in AI_VISIBILITY_SURFACES}


@dataclass
class SurfaceUsage:
    surface: str
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class CostSummary:
    """Part F.5-12 — usage/cost per surface plus total, read straight from
    the existing ai_executions/serp_executions ledgers (Groups A/B already
    log every real call there; this is a grouped read, not a new tracking
    mechanism)."""

    google: SurfaceUsage = field(default_factory=lambda: SurfaceUsage(surface="google"))
    ai_surfaces: dict[str, SurfaceUsage] = field(default_factory=dict)
    other_ai_cost_usd: float = 0.0  # classification/intent_expansion/page_gap_analysis/research_planning, etc.
    total_cost_usd: float = 0.0


def compute_cost_summary(session: Session, research_run_id: uuid.UUID) -> CostSummary:
    ai_executions = session.exec(select(AIExecution).where(AIExecution.research_run_id == research_run_id)).all()
    serp_executions = session.exec(select(SerpExecution).where(SerpExecution.research_run_id == research_run_id)).all()

    ai_surfaces: dict[str, SurfaceUsage] = defaultdict(lambda: None)  # type: ignore[arg-type]
    other_ai_cost = 0.0

    for execution in ai_executions:
        if execution.task_type != AI_VISIBILITY_TASK_TYPE:
            other_ai_cost += execution.cost_usd or 0.0
            continue
        surface_name = _SURFACE_BY_PROVIDER_MODEL.get((execution.provider, execution.model), execution.provider)
        usage = ai_surfaces.get(surface_name)
        if usage is None:
            usage = SurfaceUsage(surface=surface_name)
            ai_surfaces[surface_name] = usage
        usage.requests += 1
        usage.input_tokens += execution.input_tokens or 0
        usage.output_tokens += execution.output_tokens or 0
        usage.cost_usd += execution.cost_usd or 0.0

    google = SurfaceUsage(
        surface="google",
        requests=len(serp_executions),
        cost_usd=sum(e.cost_usd or 0.0 for e in serp_executions),
    )

    total = google.cost_usd + other_ai_cost + sum(u.cost_usd for u in ai_surfaces.values())

    return CostSummary(
        google=google, ai_surfaces=dict(ai_surfaces), other_ai_cost_usd=other_ai_cost, total_cost_usd=total
    )
