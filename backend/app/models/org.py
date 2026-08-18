import uuid

from sqlmodel import Field

from app.models.base import TimestampedModel


class Organization(TimestampedModel, table=True):
    __tablename__ = "organizations"

    name: str
    slug: str = Field(unique=True, index=True)


class User(TimestampedModel, table=True):
    __tablename__ = "users"

    organization_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)
    email: str = Field(unique=True, index=True)
    full_name: str | None = None
