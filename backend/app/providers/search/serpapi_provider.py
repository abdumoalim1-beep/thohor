import time
from urllib.parse import urlparse

import httpx

from app.core.retry import RetryExhaustedError, retry_with_backoff
from app.providers.search.base import (
    SearchProvider,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

# Part H5 — real, transient failure modes worth retrying: rate limiting and
# server-side errors. NOT retried: 4xx other than 429 (bad request, auth,
# quota-exhausted-forever — see the G-B6 live benchmark, where SerpAPI's
# actual "account has run out of searches" response IS a 429 that retrying
# can never fix; bounding attempts low keeps that cheap to fail past rather
# than pretending it's certainly transient).
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return isinstance(exc, httpx.TransportError)


def _is_rate_limit(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _safe_error_message(exc: Exception | None) -> str:
    """Never stringify an httpx request URL: it contains the API key."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} from SerpAPI"
    if isinstance(exc, httpx.TimeoutException):
        return "SerpAPI request timed out"
    if isinstance(exc, httpx.TransportError):
        return "SerpAPI transport error"
    return "SerpAPI request failed"


class SerpApiProvider(SearchProvider):
    """Real adapter for serpapi.com. Swappable for any other SERP provider
    later — nothing outside app/providers/search/ needs to know which one
    is active."""

    name = "serpapi"

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def search(self, request: SearchRequest) -> SearchResponse:
        params = {
            "engine": "google",
            "q": request.keyword,
            "gl": request.country,
            "hl": request.language,
            "num": request.num_results,
            "device": request.device,
            "api_key": self._api_key,
        }

        async def _do_request() -> tuple[dict, int]:
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(SERPAPI_ENDPOINT, params=params)
                response.raise_for_status()
                return response.json(), int((time.monotonic() - start) * 1000)

        try:
            (data, latency_ms), _outcome = await retry_with_backoff(
                _do_request, max_attempts=3, is_retryable=_is_retryable, is_rate_limit=_is_rate_limit
            )
        except RetryExhaustedError as exc:
            raise SearchProviderError(_safe_error_message(exc.__cause__)) from exc
        except httpx.HTTPError as exc:
            # Non-retryable (e.g. malformed request) — fails on the first attempt.
            raise SearchProviderError(_safe_error_message(exc)) from exc

        # Defensive: never persist the API key even if the provider ever
        # echoes request params back in the response.
        if isinstance(data.get("search_parameters"), dict):
            data["search_parameters"].pop("api_key", None)

        results: list[SearchResultItem] = []
        for item in data.get("organic_results", [])[: request.num_results]:
            link = item.get("link")
            if not link:
                continue
            results.append(
                SearchResultItem(
                    rank=item.get("position", len(results) + 1),
                    domain=urlparse(link).hostname or "",
                    url=link,
                    title=item.get("title"),
                    result_type="organic",
                )
            )

        return SearchResponse(provider=self.name, results=results, raw=data, latency_ms=latency_ms)
