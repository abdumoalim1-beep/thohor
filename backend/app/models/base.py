import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampedModel(SQLModel):
    """Base for all tables: UUID PK + immutable created_at.

    Rows are never updated in place for observation/history tables — a new
    row with a fresh created_at/observed_at represents the new state.
    """

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
