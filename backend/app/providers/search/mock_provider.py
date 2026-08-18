from app.providers.search.base import SearchProvider, SearchRequest, SearchResponse, SearchResultItem


class MockSearchProvider(SearchProvider):
    """Deterministic, network-free provider for unit tests and for running
    the full pipeline without a paid SERP key. Never used to make real
    visibility claims — only the real adapter's results should back an
    evidence-backed recommendation."""

    name = "mock"

    async def search(self, request: SearchRequest) -> SearchResponse:
        results = [
            SearchResultItem(
                rank=i + 1,
                domain=f"example-competitor-{i + 1}.test",
                url=f"https://example-competitor-{i + 1}.test/{request.keyword}",
                title=f"{request.keyword} — نتيجة {i + 1}",
            )
            for i in range(request.num_results)
        ]
        return SearchResponse(provider=self.name, results=results, raw={"mock": True}, latency_ms=1)
