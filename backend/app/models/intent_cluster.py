import uuid

from sqlmodel import Field

from app.models.base import TimestampedModel


class IntentCluster(TimestampedModel, table=True):
    """Part Q1 — groups related accepted intents beyond G-B1's
    near-duplicate rejection (which only drops near-identical phrasings of
    the *same* question). 'قهوة مختصة', 'معدات تحضير القهوة المختصة', and
    'طريقة عمل قهوة مختصة اليوم' are three distinct, all individually
    accepted intents — but they are one topic, not three unrelated
    signals. See app/intent/clustering.py for the deterministic grouping
    rule (category + content-token overlap, no AI)."""

    __tablename__ = "intent_clusters"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)
    # The accepted member intent with the highest quality_score in the
    # cluster — a real, natural phrase a customer would actually search,
    # never a synthetic "topic name".
    label: str
    category: str | None = None
    intent_count: int = Field(default=0)
