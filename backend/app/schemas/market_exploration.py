from pydantic import BaseModel, Field


class MarketExplorationRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    max_queries: int = Field(default=3, ge=1, le=3)


class MarketExplorationEstimate(BaseModel):
    max_queries: int
    estimated_serp_cost_usd: float
    includes: list[str]


class MarketExplorationResultItem(BaseModel):
    query: str
    rank: int
    domain: str
    url: str
    title: str | None = None
    entity_type: str


class MarketExplorationResponse(BaseModel):
    research_run_id: str
    status: str
    topic: str
    queries: list[str]
    results: list[MarketExplorationResultItem]
    client_ranks: dict[str, int | None]
    recurring_domains: list[dict]
    actual_serp_cost_usd: float
    warnings: list[str] = Field(default_factory=list)

