import uuid
from datetime import datetime

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel, utcnow


class Brand(TimestampedModel, table=True):
    __tablename__ = "brands"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    name: str
    aliases: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))


class Category(TimestampedModel, table=True):
    __tablename__ = "categories"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    parent_id: uuid.UUID | None = Field(default=None, foreign_key="categories.id")
    name: str
    url: str | None = None


class Product(TimestampedModel, table=True):
    __tablename__ = "products"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    category_id: uuid.UUID | None = Field(default=None, foreign_key="categories.id")
    name: str
    url: str = Field(index=True)
    price: float | None = None
    # Best-effort "was" price from schema.org AggregateOffer.highPrice only
    # — never inferred from rendered strikethrough text. None whenever the
    # page doesn't emit it (common; not every catalog structures this).
    original_price: float | None = None
    currency: str | None = None
    availability: str | None = None
    sku: str | None = None
    rating: float | None = None
    review_count: int | None = None
    # From schema.org Product/ProductGroup JSON-LD `image` only — never a
    # guessed or generated image.
    image_url: str | None = None
    # Deterministically-extracted facts only (schema.org, DOM). AI-inferred
    # attributes belong in page_observations.extracted_entities, not here.
    attributes: dict = Field(default_factory=dict, sa_column=Column(PortableJSONB))
    # created_at (from TimestampedModel) already IS "first seen" — immutable,
    # set once at insert, never touched again. last_seen_at is the one
    # genuinely new piece of state: bumped every time a re-crawl still
    # finds this product, so "still listed" vs. "not seen in the latest
    # crawl" is a real, queryable fact instead of only inferable from a
    # separate per-run join.
    last_seen_at: datetime = Field(default_factory=utcnow)


class Page(TimestampedModel, table=True):
    __tablename__ = "pages"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    url: str = Field(index=True)
    page_type: str | None = None  # category | product | content | home | other


class PageSnapshot(TimestampedModel, table=True):
    """Immutable historical snapshot of a page. Never updated — a re-crawl
    inserts a new row with a new observed_at instead of mutating this one."""

    __tablename__ = "page_snapshots"

    page_id: uuid.UUID = Field(foreign_key="pages.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)
    observed_at: datetime = Field(default_factory=utcnow)
    html_hash: str
    title: str | None = None
    h1: str | None = None
    content_hash: str | None = None
    structured_data: dict | None = Field(default=None, sa_column=Column(PortableJSONB))
    links: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    entities: dict | None = Field(default=None, sa_column=Column(PortableJSONB))
