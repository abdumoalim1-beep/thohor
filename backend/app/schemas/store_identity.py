from pydantic import BaseModel, Field


class IdentitySource(BaseModel):
    url: str
    title: str


class StoreIdentity(BaseModel):
    """Structured output for web-search-based store identity resolution —
    deliberately independent of crawled catalog data (PRD: identity
    decoupling). Every populated field must be traceable to a real web
    search result; unknown facts are null/empty, never guessed.
    """

    brand_name: str
    business_type: str | None = None
    description: str | None = None
    country: str | None = None
    city: str | None = None
    language: str | None = None
    platform: str = "unknown"  # shopify|salla|zid|custom|unknown
    categories: list[str] = Field(default_factory=list)
    target_audiences: list[str] = Field(default_factory=list)
    market_signals: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[IdentitySource] = Field(default_factory=list)
