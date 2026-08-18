import uuid

from sqlmodel import Session

from app.core.config import Settings
from app.models.evaluation import EvaluationCampaign


class CampaignBudgetExceededError(RuntimeError):
    """Raised before a live SerpAPI request would exceed the campaign's
    allocated budget or a global ceiling — the request must never be sent
    when this is raised. Mirrors LiveProviderBlockedError's 'fail clearly,
    never silently substitute' rule, one level down (campaign-scoped
    instead of dev-wide)."""


def reserve_serp_request(
    session: Session,
    campaign_id: uuid.UUID,
    settings: Settings,
    *,
    requests_this_run: int,
) -> None:
    """Called immediately before dispatching one real SerpAPI request
    inside an approved live evaluation round (see
    CampaignGuardedSearchProvider). Reserves capacity — checks every budget
    dimension and increments used_serp_requests — *before* the request
    goes out, never discovered as an overspend after the fact. Raises
    CampaignBudgetExceededError and leaves used_serp_requests unchanged
    when any dimension is exhausted."""
    campaign = session.get(EvaluationCampaign, campaign_id)
    if campaign is None:
        raise CampaignBudgetExceededError(f"evaluation_campaign {campaign_id} not found")
    if campaign.completed_at is not None:
        raise CampaignBudgetExceededError(f"campaign '{campaign.name}' is already completed — no further spend allowed")
    if campaign.used_serp_requests >= campaign.allocated_serp_budget:
        raise CampaignBudgetExceededError(
            f"campaign '{campaign.name}' has exhausted its allocated SerpAPI budget "
            f"({campaign.used_serp_requests}/{campaign.allocated_serp_budget})"
        )
    if campaign.used_serp_requests >= settings.max_live_serp_requests_per_campaign:
        raise CampaignBudgetExceededError(
            f"campaign '{campaign.name}' reached MAX_LIVE_SERP_REQUESTS_PER_CAMPAIGN "
            f"({settings.max_live_serp_requests_per_campaign})"
        )
    if requests_this_run >= settings.max_live_serp_requests_per_run:
        raise CampaignBudgetExceededError(
            f"this run reached MAX_LIVE_SERP_REQUESTS_PER_RUN ({settings.max_live_serp_requests_per_run})"
        )

    campaign.used_serp_requests += 1
    session.add(campaign)
    session.commit()
