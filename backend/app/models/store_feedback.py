import uuid

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel


class StoreFeedback(TimestampedModel, table=True):
    """User-submitted trust-gate feedback on the "متجرك" understanding
    summary — a lightweight signal, not an editing system. issues is only
    populated when feedback_type == "incorrect"."""

    __tablename__ = "store_feedback"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id")
    feedback_type: str  # "confirmed" | "incorrect"
    issues: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    note: str | None = None
