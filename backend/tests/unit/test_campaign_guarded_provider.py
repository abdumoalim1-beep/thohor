import pytest

from app.core.config import Settings
from app.evaluation.campaign_guard import CampaignBudgetExceededError
from app.models.evaluation import EvaluationCampaign
from app.providers.search.base import SearchProvider, SearchRequest, SearchResponse, SearchResultItem
from app.providers.search.campaign_guarded_provider import CampaignGuardedSearchProvider
from app.providers.search.pricing import estimate_search_cost_usd
from app.providers.search.serpapi_provider import SerpApiProvider


class _FakeInnerProvider(SearchProvider):
    name = "fake-inner"

    def __init__(self):
        self.call_count = 0

    async def search(self, request: SearchRequest) -> SearchResponse:
        self.call_count += 1
        return SearchResponse(provider=self.name, results=[SearchResultItem(rank=1, domain="x.test", url="https://x.test")])


def _settings(**overrides) -> Settings:
    defaults = dict(max_live_serp_requests_per_campaign=250, max_live_serp_requests_per_run=30)
    defaults.update(overrides)
    return Settings(**defaults)


def _make_campaign(session, **overrides) -> EvaluationCampaign:
    defaults = dict(name="FINAL_VALIDATION_1", allocated_serp_budget=2)
    defaults.update(overrides)
    campaign = EvaluationCampaign(**defaults)
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


async def test_campaign_guarded_provider_forwards_to_inner_and_increments_budget(session):
    campaign = _make_campaign(session)
    inner = _FakeInnerProvider()
    provider = CampaignGuardedSearchProvider(inner, session, campaign.id, _settings())

    response = await provider.search(SearchRequest(keyword="x", country="sa", language="ar"))

    assert inner.call_count == 1
    assert response.results[0].domain == "x.test"
    session.refresh(campaign)
    assert campaign.used_serp_requests == 1


async def test_campaign_guarded_provider_blocks_before_calling_inner_once_exhausted(session):
    campaign = _make_campaign(session, allocated_serp_budget=1)
    inner = _FakeInnerProvider()
    provider = CampaignGuardedSearchProvider(inner, session, campaign.id, _settings())

    await provider.search(SearchRequest(keyword="a", country="sa", language="ar"))
    with pytest.raises(CampaignBudgetExceededError):
        await provider.search(SearchRequest(keyword="b", country="sa", language="ar"))

    # The inner provider was never called for the second, blocked request.
    assert inner.call_count == 1


def test_campaign_guarded_provider_does_not_shadow_the_real_providers_identity(session):
    """Part R4 (Round 1 remediation) — CampaignGuardedSearchProvider.name is
    deliberately "campaign-guarded" (it IS a distinct wrapper), but that
    must never leak into cost/DB attribution: those must resolve to the
    real underlying provider ('serpapi'), or cost silently defaults to 0.0
    (pricing.py has no entry for 'campaign-guarded'). No real SerpAPI call
    is made here — only identity resolution is under test."""
    campaign = _make_campaign(session)
    real_provider = SerpApiProvider(api_key="fake-key-never-used")
    guarded = CampaignGuardedSearchProvider(real_provider, session, campaign.id, _settings())

    assert guarded.name == "campaign-guarded"
    assert guarded.underlying_provider_name == "serpapi"
    assert estimate_search_cost_usd(guarded.underlying_provider_name) > 0.0
    # The bug this guards against: attributing cost by the wrapper's own
    # shadowing `.name` silently produces 0.0 for every campaign-guarded
    # search, because pricing.py has no "campaign-guarded" entry.
    assert estimate_search_cost_usd(guarded.name) == 0.0
