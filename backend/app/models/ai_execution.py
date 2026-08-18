import uuid
from enum import Enum

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel


class AIExecutionStatus(str, Enum):
    success = "success"
    error = "error"
    fallback = "fallback"
    cache_hit = "cache_hit"


class AIExecution(TimestampedModel, table=True):
    """One record per AIProvider.generate() call, regardless of which
    provider/model served it. This is the usage & cost ledger — every AI
    call in the system must produce exactly one row here."""

    __tablename__ = "ai_executions"

    research_run_id: uuid.UUID | None = Field(default=None, foreign_key="research_runs.id", index=True)
    agent_run_id: uuid.UUID | None = Field(default=None, foreign_key="agent_runs.id", index=True)

    provider: str = Field(index=True)  # openai | anthropic | google | mock
    model: str
    task_type: str = Field(index=True)  # classification | entity_extraction | ...

    prompt_name: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None

    # sha256 of the normalized input — used for caching and for
    # deduplicating identical requests across runs.
    input_hash: str = Field(index=True)

    raw_artifact_uri: str | None = None  # raw provider response in MinIO
    parsed_output: dict | None = Field(default=None, sa_column=Column(PortableJSONB))

    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None

    status: AIExecutionStatus = Field(default=AIExecutionStatus.success)
    error: str | None = None
