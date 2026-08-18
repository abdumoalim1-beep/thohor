import uuid
from datetime import datetime

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel, utcnow


class PromptFamily(TimestampedModel, table=True):
    """Groups the natural-language prompt variants generated for one
    intent — mirrors intent_keywords' relationship shape (PRD section 46:
    prompt_families/prompt_variants)."""

    __tablename__ = "prompt_families"

    intent_id: uuid.UUID = Field(foreign_key="intents.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)
    agent_run_id: uuid.UUID | None = Field(default=None, foreign_key="agent_runs.id")


class PromptVariant(TimestampedModel, table=True):
    """One natural-language question a real customer might ask an AI
    assistant (PRD section 19) — not a keyword."""

    __tablename__ = "prompt_variants"

    prompt_family_id: uuid.UUID = Field(foreign_key="prompt_families.id", index=True)
    text: str


class AIVisibilityObservation(TimestampedModel, table=True):
    """One row per (prompt_variant, engine, repetition) probe — the AI Test
    Matrix cell (PRD section 20-21). mentioned/citations/linked_domains are
    derived deterministically from the raw response text via programmatic
    entity matching, never by asking another AI call to judge the first
    one. Immutable: every probe is a fresh row, never updated.
    """

    __tablename__ = "ai_visibility_observations"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    intent_id: uuid.UUID = Field(foreign_key="intents.id", index=True)
    stable_intent_id: uuid.UUID | None = Field(default=None, foreign_key="stable_intents.id", index=True)
    prompt_variant_id: uuid.UUID = Field(foreign_key="prompt_variants.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)
    agent_run_id: uuid.UUID | None = Field(default=None, foreign_key="agent_runs.id")
    ai_execution_id: uuid.UUID | None = Field(default=None, foreign_key="ai_executions.id", index=True)
    # Same Control/Discovery separation as SerpObservation.origin_task_id
    # (see app/models/serp.py) — NULL for the fixed ai_visibility_batch
    # phase, set for Discovery-triggered probes (e.g. validate_finding).
    origin_task_id: uuid.UUID | None = Field(default=None, foreign_key="research_tasks.id", index=True)

    # Part H1 (post-G-B directive) — set only when this row was produced by
    # EvaluationMode.replay copying a real prior probe instead of making a
    # new AI call (ai_execution_id stays NULL in that case, since no new
    # ai_executions row was created). NULL means this observation came from
    # a genuine fresh call. Keeps "was this freshly measured or replayed?"
    # an explicit, queryable fact on the row itself, never just implied.
    replayed_from_observation_id: uuid.UUID | None = Field(
        default=None, foreign_key="ai_visibility_observations.id", index=True
    )

    # Part F.5-2: provider is the API vendor (openai/anthropic/google);
    # surface is the consumer product being measured (chatgpt/gemini/claude)
    # — see app/ai_visibility/surfaces.py. They map 1:1 today but are
    # tracked separately so a future surface on an existing provider (or a
    # provider offering multiple surfaces) never needs a schema change.
    surface: str = Field(default="", index=True)
    provider: str = Field(index=True)
    model: str
    search_enabled: bool = Field(default=False)
    grounding_enabled: bool = Field(default=False)
    citations_available: bool = Field(default=False)
    country: str
    language: str
    repetition_index: int = Field(default=0)
    observed_at: datetime = Field(default_factory=utcnow)

    mentioned: bool = Field(default=False)
    mention_position: int | None = None
    competitors_mentioned: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    products_mentioned: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    citations: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    linked_domains: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    cited_domains: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    raw_artifact_uri: str | None = None
