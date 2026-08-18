import uuid

from sqlmodel import Session, select

from app.models.ai_execution import AIExecution
from app.models.serp import SerpExecution


def snapshot_usage(session: Session, research_run_id: uuid.UUID) -> dict:
    """Point-in-time totals from the existing cost ledgers (ai_executions,
    serp_executions). The iterative loop diffs two snapshots around each
    task execution to attribute real, already-tracked usage/cost to that
    task — no separate bookkeeping needed inside each worker."""
    ai_executions = session.exec(select(AIExecution).where(AIExecution.research_run_id == research_run_id)).all()
    serp_executions = session.exec(select(SerpExecution).where(SerpExecution.research_run_id == research_run_id)).all()
    return {
        "ai_cost": sum(e.cost_usd or 0.0 for e in ai_executions),
        "ai_count": len(ai_executions),
        "tokens": sum((e.input_tokens or 0) + (e.output_tokens or 0) for e in ai_executions),
        "search_cost": sum(e.cost_usd or 0.0 for e in serp_executions),
        "search_count": len(serp_executions),
    }
