import uuid
from enum import Enum

from sqlmodel import Field

from app.models.base import TimestampedModel


class AlertStatus(str, Enum):
    unread = "unread"
    read = "read"
    dismissed = "dismissed"


class Alert(TimestampedModel, table=True):
    """A deterministic, rule-generated notice (Group F8) — alert_type is a
    plain string (not enum) for the same extensibility reason as
    Opportunity.opportunity_type: new alert rules never need a schema
    migration to add."""

    __tablename__ = "alerts"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id")

    alert_type: str = Field(index=True)
    severity: str = Field(default="info")
    title: str
    message: str
    related_recommendation_id: uuid.UUID | None = Field(default=None, foreign_key="recommendations.id")
    related_competitor_id: uuid.UUID | None = Field(default=None, foreign_key="competitors.id")

    status: AlertStatus = Field(default=AlertStatus.unread)
