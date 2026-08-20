from pydantic import BaseModel, Field


class PreviewStoreUnderstanding(BaseModel):
    """Structured output for the PreviewReport's single normalization call
    (spec Stage 3) — organizes already-extracted deterministic facts into a
    simple shape, never invents brand_name/products/category beyond what was
    actually crawled. Deliberately smaller than StoreClassification (no
    audience/attributes/confidence) — the MVP only needs enough to generate
    good search queries, not a full brand profile.

    is_online_store: judged from the same crawled page content already in
    this call's context (not a second call) — lets the frontend say
    "متجرك" only when that's actually true and "علامتك" otherwise, instead
    of assuming every analyzed site sells products online. A real
    judgment, not just "products list non-empty": the crawl can miss real
    product pages (blocked, unusual structure) on a site that genuinely is
    a store, so this catches cases the product-count heuristic alone
    would get wrong."""

    brand_name: str
    category: str
    products: list[str] = Field(default_factory=list)
    is_online_store: bool
