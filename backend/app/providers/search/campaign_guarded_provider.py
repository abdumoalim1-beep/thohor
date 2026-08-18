import uuid

from sqlmodel import Session

from app.core.config import Settings
from app.evaluation.campaign_guard import reserve_serp_request
from app.providers.search.base import SearchProvider, SearchRequest, SearchResponse


class CampaignGuardedSearchProvider(SearchProvider):
    """Wraps a real (live) SearchProvider so every request first reserves
    capacity against an approved EvaluationCampaign's SerpAPI budget — Part
    H3. Only ever wraps a live provider; mock/replay never touch the
    network and so never need budget protection."""

    name = "campaign-guarded"

    def __init__(self, inner: SearchProvider, session: Session, campaign_id: uuid.UUID, settings: Settings):
        self._inner = inner
        self._session = session
        self._campaign_id = campaign_id
        self._settings = settings
        self._requests_this_run = 0

    @property
    def underlying_provider_name(self) -> str:
        """Part R4 (Round 1 remediation) — delegates to the wrapped
        provider (recursively, in case of nested wrappers) so cost/DB
        attribution resolves to the real provider ('serpapi'), never this
        wrapper's own 'campaign-guarded' identity."""
        return self._inner.underlying_provider_name

    async def search(self, request: SearchRequest) -> SearchResponse:
        reserve_serp_request(
            self._session, self._campaign_id, self._settings, requests_this_run=self._requests_this_run
        )
        self._requests_this_run += 1
        return await self._inner.search(request)
