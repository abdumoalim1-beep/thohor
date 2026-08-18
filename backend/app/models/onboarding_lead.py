import uuid

from sqlmodel import Field

from app.models.base import TimestampedModel


class OnboardingLead(TimestampedModel, table=True):
    """A real join-trial request submitted at the end of the /signup
    onboarding wizard — tied to the store URL just analyzed and the run
    whose result the visitor saw when they asked to join."""

    __tablename__ = "onboarding_leads"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    research_run_id: uuid.UUID | None = Field(default=None, foreign_key="research_runs.id")
    name: str
    contact: str
