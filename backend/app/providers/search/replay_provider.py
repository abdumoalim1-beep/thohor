from sqlmodel import Session, select

from app.models.intent import Keyword
from app.models.serp import SerpObservation
from app.providers.search.base import (
    SearchProvider,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)


class ReplaySearchProvider(SearchProvider):
    """Serves a real, previously-collected serp_observations row instead of
    making a new SerpAPI call — zero network cost. The data is genuinely
    real (not synthetic like MockSearchProvider); only its *freshness* is
    historical. Matches on keyword text + country + language, most recent
    observation first — the same targeting a fresh SearchRequest would use.

    Takes an injected Session (same DI pattern as every other DB-touching
    function in this codebase — never a global engine import) so it works
    against the test SQLite session in unit tests and the real session in
    production alike.

    Raises SearchProviderError (never returns empty/synthetic results) when
    no matching historical observation exists — an honest 'we don't have
    this in replay' signal instead of a silent, misleading fallback. Callers
    already handle a failed search gracefully (one task/agent_run failing
    doesn't stop the run), matching how a real provider outage is handled.
    """

    name = "replay"

    def __init__(self, session: Session):
        self._session = session

    async def search(self, request: SearchRequest) -> SearchResponse:
        keyword = self._session.exec(
            select(Keyword)
            .where(Keyword.text == request.keyword)
            .where(Keyword.country == request.country)
            .where(Keyword.language == request.language)
        ).first()
        if keyword is None:
            raise SearchProviderError(
                f"replay: no historical keyword match for '{request.keyword}' ({request.country}/{request.language})"
            )

        observation = self._session.exec(
            select(SerpObservation)
            .where(SerpObservation.keyword_id == keyword.id)
            .order_by(SerpObservation.observed_at.desc())  # type: ignore[arg-type]
        ).first()
        if observation is None:
            raise SearchProviderError(f"replay: no historical serp_observation for keyword '{request.keyword}'")

        results = [
            SearchResultItem(
                rank=r.get("rank", i + 1),
                domain=r.get("domain", ""),
                url=r.get("url", ""),
                title=r.get("title"),
                result_type=r.get("result_type", "organic"),
            )
            for i, r in enumerate(observation.results[: request.num_results])
            if r.get("domain")
        ]

        return SearchResponse(
            provider=self.name,
            results=results,
            raw={
                "replay": True,
                "source_observation_id": str(observation.id),
                "observed_at": observation.observed_at.isoformat(),
            },
            latency_ms=0,
        )
