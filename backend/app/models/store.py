import uuid
from datetime import datetime
from enum import Enum

from sqlmodel import Field

from app.models.base import TimestampedModel


class StoreStatus(str, Enum):
    pending = "pending"
    active = "active"
    archived = "archived"


class Store(TimestampedModel, table=True):
    __tablename__ = "stores"

    organization_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)
    url: str = Field(index=True)
    # Part R2-F1 (Round 2 remediation) — country/language are the RESOLVED
    # locale (see app.crawler.locale_detection), set once a crawl runs;
    # never invented up front. market/locale_confidence/locale_source/
    # locale_status make the resolution auditable instead of a silent
    # sa/ar default (the confirmed root cause of Round 2's glossier.com/
    # chewy.com failures — real US stores measured as if Saudi/Arabic).
    country: str | None = None
    language: str | None = None
    market: str | None = None
    locale_confidence: float | None = None
    locale_source: str | None = None
    # "resolved" | "unresolved" — plain str (not a Python/Postgres enum),
    # matching Competitor.classification's own precedent, to sidestep the
    # ALTER TYPE migration pain documented repeatedly elsewhere in this
    # codebase for genuine enum columns.
    locale_status: str = Field(default="unresolved")
    # Detected by the crawler (Part G-B5 —
    # app.crawler.platform_detection.detect_platform_from_pages, run inside
    # run_crawl_agent) from deterministic HTML markers: shopify/salla/zid/
    # woocommerce today. Never a required onboarding input, per the
    # platform-agnostic principle; stays None if no known marker is found
    # (honest 'unknown', never guessed by AI).
    platform_hint: str | None = None
    status: StoreStatus = Field(default=StoreStatus.pending)

    # Group F7 — scheduled/continuous research. Plain string (not enum) so
    # cadence options stay configurable without a migration, matching
    # Opportunity.opportunity_type's rationale.
    monitoring_cadence: str = Field(default="weekly")
    next_scheduled_run_at: datetime | None = None

    # Identity decoupling — tracked separately from catalog/competitor
    # state (never conflated): identity_* is about "do we know the brand
    # name and activity", independent of whether the catalog crawl
    # succeeded. business_type/categories themselves deliberately stay off
    # this model — they live in the store_identity_agent_run's findings,
    # same convention as ai_classification_agent_run.
    identity_source: str | None = None  # "web_search" | "crawl" | None
    identity_confidence: float | None = None
    last_identity_scan_at: datetime | None = None

    # "pending" | "scanning" | "ready" | "partial" | "blocked" | "failed"
    catalog_status: str = Field(default="pending")
    catalog_pages_crawled: int = Field(default=0)
    catalog_products_found: int = Field(default=0)
    last_catalog_scan_at: datetime | None = None

    # "pending" | "running" | "completed" | "failed"
    competitor_discovery_status: str = Field(default="pending")
    last_competitor_scan_at: datetime | None = None
