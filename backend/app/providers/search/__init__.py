import uuid

from sqlmodel import Session

from app.core.config import get_settings
from app.core.evaluation_mode import EvaluationMode, LiveProviderBlockedError
from app.providers.search.base import SearchProvider
from app.providers.search.campaign_guarded_provider import CampaignGuardedSearchProvider
from app.providers.search.mock_provider import MockSearchProvider
from app.providers.search.replay_provider import ReplaySearchProvider
from app.providers.search.serpapi_provider import SerpApiProvider

__all__ = ["SearchProvider", "get_search_provider"]


def get_search_provider(session: Session | None = None, campaign_id: uuid.UUID | None = None) -> SearchProvider:
    """Mode-aware factory (post-G-B directive) — no silent fallback between
    modes. mock/replay never touch the network; live requires both a real
    key and the dev-live-SerpAPI guard to be explicitly opened (Settings.
    dev_live_serp_budget / live_serp_override), raising LiveProviderBlockedError
    otherwise rather than quietly downgrading to mock or replay data.

    `session` is required when evaluation_mode=replay (ReplaySearchProvider
    reads real historical serp_observations via the caller's session — same
    DI pattern as every other DB-touching function here, never a global
    engine import) and ignored otherwise.

    `campaign_id` (Part H3) — when set, live requests are wrapped in
    CampaignGuardedSearchProvider so every real search reserves capacity
    against that EvaluationCampaign's allocated SerpAPI budget first.
    Requires `session` too. Not required for mock/replay (they never spend
    campaign budget)."""
    settings = get_settings()

    if settings.evaluation_mode == EvaluationMode.mock:
        return MockSearchProvider()

    if settings.evaluation_mode == EvaluationMode.replay:
        if session is None:
            raise ValueError("get_search_provider(session=...) is required when evaluation_mode=replay")
        return ReplaySearchProvider(session)

    # live
    if not settings.serpapi_api_key:
        raise LiveProviderBlockedError("EVALUATION_MODE=live but no SERPAPI_API_KEY is configured")
    if settings.dev_live_serp_budget <= 0 and not settings.live_serp_override:
        raise LiveProviderBlockedError(
            "Live SerpAPI calls are blocked by default (dev_live_serp_budget=0). "
            "Set DEV_LIVE_SERP_BUDGET>0 or LIVE_SERP_OVERRIDE=true explicitly to spend real search credits."
        )
    provider: SearchProvider = SerpApiProvider(api_key=settings.serpapi_api_key.get_secret_value())
    if campaign_id is not None:
        if session is None:
            raise ValueError("get_search_provider(session=...) is required when campaign_id is set")
        provider = CampaignGuardedSearchProvider(provider, session, campaign_id, settings)
    return provider
