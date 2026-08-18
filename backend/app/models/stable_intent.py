import re
import uuid

from sqlmodel import Field

from app.models.base import TimestampedModel


def normalize_topic(topic: str) -> str:
    """Canonicalization used both to create/match a StableIntent and to
    backfill historical Intent rows onto one — lowercase, collapse
    whitespace, strip punctuation. Deliberately simple (no embeddings/
    semantic matching in V1): the same detection method must be usable
    both live and inside an Alembic data migration."""
    lowered = topic.strip().lower()
    stripped = re.sub(r"[^\w\s]", "", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", stripped).strip()


class StableIntent(TimestampedModel, table=True):
    """A search intent's identity that survives across research runs.

    Intent rows (app/models/intent.py) are still created fresh every
    research run — that immutability is unchanged. StableIntent is the
    thing that stays the same: every run-specific Intent that represents
    'the same real-world question' (matched by normalized_topic within a
    store+locale) points at the same StableIntent row. This is what lets
    Recommendation.target_intents, and any SERP/AI-visibility observation,
    remain meaningful across a Recommendation's entire lifecycle instead of
    going stale the moment a new research_run regenerates its Intent rows.
    """

    __tablename__ = "stable_intents"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)

    canonical_topic: str
    normalized_topic: str = Field(index=True)
    country: str
    language: str
    locale: str = Field(index=True)  # f"{country}_{language}", denormalized for fast lookup
    intent_type: str | None = None  # free-text, e.g. Intent.category — not hardcoded (same rationale as opportunity_type)
