import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models.ai_execution import AIExecution
from app.models.evaluation import EvaluationCampaign
from app.models.finding import Finding
from app.models.recommendation import Recommendation
from app.models.research import ResearchRun
from app.models.serp import SerpExecution
from app.models.store import Store


@dataclass
class CampaignCostReport:
    """Part H3 item #34 — internal cost visibility for one evaluation
    campaign, spanning every research_run for the campaign's stores that
    started at/after the campaign's started_at (and before completed_at,
    once set). Never a product-facing artifact."""

    campaign_name: str
    serp_requests_used: int
    serp_budget_remaining: int
    openai_requests: int
    openai_tokens: int
    openai_cost_usd: float
    total_cost_usd: float
    store_count: int
    cost_per_store: float | None
    cost_per_useful_finding: float | None
    cost_per_recommendation: float | None


def _campaign_research_run_ids(session: Session, campaign: EvaluationCampaign) -> list[uuid.UUID]:
    if not campaign.stores:
        return []
    store_ids = [uuid.UUID(s) for s in campaign.stores]
    query = select(ResearchRun).where(ResearchRun.store_id.in_(store_ids))  # type: ignore[attr-defined]
    if campaign.started_at is not None:
        query = query.where(ResearchRun.created_at >= campaign.started_at)  # type: ignore[attr-defined]
    if campaign.completed_at is not None:
        query = query.where(ResearchRun.created_at <= campaign.completed_at)  # type: ignore[attr-defined]
    runs = session.exec(query).all()
    return [r.id for r in runs]


def compute_campaign_cost_report(session: Session, campaign_id: uuid.UUID) -> CampaignCostReport:
    campaign = session.get(EvaluationCampaign, campaign_id)
    if campaign is None:
        raise ValueError(f"evaluation_campaign {campaign_id} not found")

    run_ids = _campaign_research_run_ids(session, campaign)

    ai_executions: list[AIExecution] = []
    serp_executions: list[SerpExecution] = []
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    if run_ids:
        ai_executions = session.exec(
            select(AIExecution).where(AIExecution.research_run_id.in_(run_ids))  # type: ignore[attr-defined]
        ).all()
        serp_executions = session.exec(
            select(SerpExecution).where(SerpExecution.research_run_id.in_(run_ids))  # type: ignore[attr-defined]
        ).all()
        findings = session.exec(select(Finding).where(Finding.research_run_id.in_(run_ids))).all()  # type: ignore[attr-defined]
        recommendations = session.exec(
            select(Recommendation).where(Recommendation.first_seen_research_run_id.in_(run_ids))  # type: ignore[attr-defined]
        ).all()

    openai_requests = sum(1 for e in ai_executions if e.provider == "openai")
    openai_tokens = sum((e.input_tokens or 0) + (e.output_tokens or 0) for e in ai_executions if e.provider == "openai")
    openai_cost = sum(e.cost_usd or 0.0 for e in ai_executions if e.provider == "openai")
    ai_cost_total = sum(e.cost_usd or 0.0 for e in ai_executions)
    serp_cost_total = sum(e.cost_usd or 0.0 for e in serp_executions)
    total_cost = ai_cost_total + serp_cost_total

    store_count = len(campaign.stores)
    useful_findings = sum(1 for f in findings if f.status.value in ("supported", "validated"))

    return CampaignCostReport(
        campaign_name=campaign.name,
        serp_requests_used=campaign.used_serp_requests,
        serp_budget_remaining=campaign.remaining_budget,
        openai_requests=openai_requests,
        openai_tokens=openai_tokens,
        openai_cost_usd=openai_cost,
        total_cost_usd=total_cost,
        store_count=store_count,
        cost_per_store=(total_cost / store_count) if store_count else None,
        cost_per_useful_finding=(total_cost / useful_findings) if useful_findings else None,
        cost_per_recommendation=(total_cost / len(recommendations)) if recommendations else None,
    )
