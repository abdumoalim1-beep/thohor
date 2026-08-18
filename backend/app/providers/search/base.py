from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    keyword: str
    country: str
    language: str
    device: str = "desktop"
    num_results: int = 10


class SearchResultItem(BaseModel):
    rank: int
    domain: str
    url: str
    title: str | None = None
    result_type: str = "organic"


class SearchResponse(BaseModel):
    provider: str
    results: list[SearchResultItem] = Field(default_factory=list)
    raw: dict | None = None
    latency_ms: int = 0


class SearchProviderError(RuntimeError):
    pass


class SearchProvider(ABC):
    """Unified interface every SERP adapter implements — mirrors AIProvider
    (app/providers/ai/base.py). Business logic must go through this
    interface, never a provider SDK directly."""

    name: str

    @property
    def underlying_provider_name(self) -> str:
        """Part R4 (Round 1 remediation) — the identity cost/analytics
        attribution should key on. Equal to `name` for a real adapter, but
        a decorator/wrapper (e.g. CampaignGuardedSearchProvider) overrides
        this to delegate to the provider it wraps, so the wrapper's own
        `name` never shadows the real provider's for pricing/DB purposes."""
        return self.name

    @abstractmethod
    async def search(self, request: SearchRequest) -> SearchResponse: ...
