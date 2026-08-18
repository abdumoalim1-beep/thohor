import pytest

from app.core.config import Settings
from app.evaluation.campaign_guard import CampaignBudgetExceededError, reserve_serp_request
from app.models.evaluation import EvaluationCampaign


def _settings(**overrides) -> Settings:
    defaults = dict(max_live_serp_requests_per_campaign=250, max_live_serp_requests_per_run=30)
    defaults.update(overrides)
    return Settings(**defaults)


def _make_campaign(session, **overrides) -> EvaluationCampaign:
    defaults = dict(name="FINAL_VALIDATION_1", allocated_serp_budget=250)
    defaults.update(overrides)
    campaign = EvaluationCampaign(**defaults)
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def test_reserve_serp_request_increments_used_requests(session):
    campaign = _make_campaign(session)
    reserve_serp_request(session, campaign.id, _settings(), requests_this_run=0)

    session.refresh(campaign)
    assert campaign.used_serp_requests == 1
    assert campaign.remaining_budget == 249


def test_reserve_serp_request_raises_when_allocated_budget_exhausted(session):
    campaign = _make_campaign(session, allocated_serp_budget=1, used_serp_requests=1)
    with pytest.raises(CampaignBudgetExceededError):
        reserve_serp_request(session, campaign.id, _settings(), requests_this_run=0)

    session.refresh(campaign)
    assert campaign.used_serp_requests == 1  # unchanged — never incremented past the block


def test_reserve_serp_request_raises_when_completed(session):
    from app.models.base import utcnow

    campaign = _make_campaign(session, completed_at=utcnow())
    with pytest.raises(CampaignBudgetExceededError):
        reserve_serp_request(session, campaign.id, _settings(), requests_this_run=0)


def test_reserve_serp_request_raises_when_per_run_limit_hit(session):
    campaign = _make_campaign(session)
    with pytest.raises(CampaignBudgetExceededError):
        reserve_serp_request(session, campaign.id, _settings(max_live_serp_requests_per_run=5), requests_this_run=5)


def test_reserve_serp_request_raises_when_missing_campaign(session):
    import uuid

    with pytest.raises(CampaignBudgetExceededError):
        reserve_serp_request(session, uuid.uuid4(), _settings(), requests_this_run=0)
