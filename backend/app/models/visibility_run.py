import uuid
from datetime import datetime

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel, utcnow


class VisibilityQuestion(TimestampedModel, table=True):
    """A natural buyer question ("أفضل متجر ورد في الرياض؟") this store
    should be checked against on AI engines — persistent and store-scoped,
    deliberately distinct from Intent/PromptFamily/PromptVariant (Phase 5
    plan): those are SEO-keyword-shaped and recreated every research_run,
    these are natural questions a real buyer would ask an AI assistant and
    persist across runs so week-over-week tracking (Phase 17) has something
    stable to compare.

    category is a plain string, not a Postgres enum, on purpose — see
    Competitor.confirmation_status's comment for why a closed enum here has
    already cost a manual-migration tax elsewhere in this same session.
    Valid values today: app.schemas.visibility_question.QUESTION_CATEGORIES.
    """

    __tablename__ = "visibility_questions"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    text: str
    category: str = Field(index=True)
    # normalize_topic(text) — dedup key so re-running generation on a store
    # that already has this exact question (modulo punctuation/case/
    # whitespace) doesn't create a near-duplicate row.
    normalized_text: str = Field(index=True)
    source_research_run_id: uuid.UUID = Field(foreign_key="research_runs.id")
    is_active: bool = Field(default=True)


class VisibilityRun(TimestampedModel, table=True):
    """MVP-1 (Part 2, re-scoped) — one execution wave: every active
    VisibilityQuestion for a store, run once each through however many
    engines are actually configured. Deliberately not tied to a
    ResearchRun — this is a separate, its-own-cadence lifecycle (triggered
    on-demand or weekly), not a step inside the 9-step research pipeline.
    """

    __tablename__ = "visibility_runs"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    status: str = Field(default="running", index=True)  # running|completed|failed
    engines_attempted: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    questions_count: int = Field(default=0)
    # SIGNUP re-scope (90-search UX) — the fixed operation budget this run
    # planned at start (up to 60 ChatGPT + up to 30 Google, honestly lower
    # when fewer questions exist). The frontend's single "تم تحليل X من 90"
    # counter polls completed EngineAnswer rows against this, never a
    # hardcoded "90" — a store with fewer generated questions shows its real
    # smaller total instead of a fabricated one.
    total_operations_planned: int = Field(default=0)
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None


class EngineAnswer(TimestampedModel, table=True):
    """One row per (question, engine) per VisibilityRun — every attempted
    cell gets an explicit row, success or failure, never silently dropped
    (so 'one engine failing' is visible, not just absent). raw_answer is
    stored inline (not just an artifact-store pointer) so it can be
    re-analyzed later without re-querying the engine. sources[] comes
    directly from the web_search tool call itself when the engine used one
    — real citations, not a separate extraction step."""

    __tablename__ = "engine_answers"

    visibility_run_id: uuid.UUID = Field(foreign_key="visibility_runs.id", index=True)
    question_id: uuid.UUID = Field(foreign_key="visibility_questions.id", index=True)
    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    engine: str = Field(index=True)  # "chatgpt" today; "perplexity"/"gemini"/"claude" later
    engine_model: str
    status: str  # success|failed
    raw_answer: str | None = None
    sources: list[dict] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    language: str | None = None
    country: str | None = None
    executed_at: datetime = Field(default_factory=utcnow)
    ai_execution_id: uuid.UUID | None = None


class EngineAnswerAnalysis(TimestampedModel, table=True):
    """1:1 with EngineAnswer — kept as a separate table on purpose (same
    'what happened' vs 'what we concluded' split already used elsewhere,
    e.g. PageObservation vs Evidence). This is the one place in the
    codebase where a semantic AI judgment (mention vs recommendation vs
    warned-against) substitutes for deterministic extraction — a
    deliberate, flagged exception (Phase 12's original design note),
    which is exactly why evidence_quote is mandatory: every classification
    must be traceable back to the actual text that produced it."""

    __tablename__ = "engine_answer_analyses"

    engine_answer_id: uuid.UUID = Field(foreign_key="engine_answers.id", index=True, unique=True)
    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    brand_mentioned: bool
    mention_type: str  # recommended|mere_mention|not_mentioned|comparison_inclusion|warned_against
    mention_rank: int | None = None
    recommendation_rank: int | None = None
    competitors_mentioned: list[dict] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    evidence_quote: str | None = None
    confidence: float
