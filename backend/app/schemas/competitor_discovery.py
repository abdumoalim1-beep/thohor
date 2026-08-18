from pydantic import BaseModel, Field


class DiscoveredCompetitorSource(BaseModel):
    url: str
    title: str


class DiscoveredCompetitor(BaseModel):
    """One web-search-identified competitor. Every populated field must be
    traceable to a real search result in `sources`; unknown facts are
    null/empty, never guessed — same discipline as StoreIdentity."""

    name: str
    domain: str
    description: str | None = None
    categories: list[str] = Field(default_factory=list)
    market: str | None = None  # e.g. محلي/إقليمي/دولي
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[DiscoveredCompetitorSource] = Field(default_factory=list)


class CompetitorDiscoveryResult(BaseModel):
    competitors: list[DiscoveredCompetitor] = Field(default_factory=list)
