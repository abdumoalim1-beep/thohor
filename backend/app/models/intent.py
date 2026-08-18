import uuid
from enum import Enum

from sqlmodel import Field

from app.models.base import TimestampedModel


class CommercialStage(str, Enum):
    awareness = "awareness"
    consideration = "consideration"
    purchase = "purchase"


class DemandLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class IntentSource(str, Enum):
    deterministic_catalog = "deterministic_catalog"
    ai_expansion = "ai_expansion"


class Intent(TimestampedModel, table=True):
    """A search intent — the product's core unit (PRD section 15), not a
    keyword. Immutable once created: a later research_run adds new intents
    rather than editing these. stable_intent_id is what carries identity
    across that regeneration (see app/models/stable_intent.py) — every
    Intent row that represents the same real-world question across
    different research_runs points at the same StableIntent."""

    __tablename__ = "intents"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)
    stable_intent_id: uuid.UUID | None = Field(default=None, foreign_key="stable_intents.id", index=True)

    topic: str
    category: str | None = None
    commercial_stage: CommercialStage | None = None
    country: str
    language: str
    relevance: float | None = None
    estimated_demand: DemandLevel | None = None
    competition: float | None = None
    confidence: float = Field(default=1.0)
    source: IntentSource = Field(index=True)

    # Part G-B1 — deterministic quality gate (app/intent/quality.py). A
    # rejected Intent row is kept for traceability (never erased — same
    # "immutable, explain why" principle as everything else in this
    # project) but is_accepted=False means it never reaches the Control/
    # Research Set (SERP measurement, prompt families, opportunities).
    intent_type: str | None = Field(default=None, index=True)
    quality_score: float = Field(default=1.0)
    quality_reason: str | None = None
    is_accepted: bool = Field(default=True, index=True)

    # Part Q1 — set by app.intent.clustering.cluster_intents right after
    # the quality gate; only accepted intents ever get one. NULL for
    # rejected intents and for any run predating this feature.
    cluster_id: uuid.UUID | None = Field(default=None, foreign_key="intent_clusters.id", index=True)


class Keyword(TimestampedModel, table=True):
    """Shared/reusable keyword text — deduplicated by (text, country,
    language) so the same phrase discovered for multiple intents/stores
    doesn't create duplicate rows."""

    __tablename__ = "keywords"

    text: str = Field(index=True)
    country: str
    language: str


class IntentKeyword(TimestampedModel, table=True):
    """Join table: which keywords belong to which intent. is_primary marks
    the one keyword actually measured in SERP (budget control — PRD
    section 50 cost control applies to paid SERP calls too)."""

    __tablename__ = "intent_keywords"

    intent_id: uuid.UUID = Field(foreign_key="intents.id", index=True)
    keyword_id: uuid.UUID = Field(foreign_key="keywords.id", index=True)
    is_primary: bool = Field(default=False)
