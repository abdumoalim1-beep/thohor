from pydantic import BaseModel, Field


class PreviewStoreUnderstanding(BaseModel):
    """Structured output for the PreviewReport's single normalization call
    (spec Stage 3) — organizes already-extracted deterministic facts into a
    simple shape, never invents brand_name/products/category beyond what was
    actually crawled. Deliberately smaller than StoreClassification (no
    audience/attributes/confidence) — the MVP only needs enough to generate
    good search queries, not a full brand profile."""

    brand_name: str
    category: str
    products: list[str] = Field(default_factory=list)
