from pydantic import BaseModel, Field, field_validator

MENTION_TYPES = frozenset({
    "recommended", "mere_mention", "not_mentioned", "comparison_inclusion", "warned_against",
})


def _clamp_rank_to_none_below_one(value: int | None) -> int | None:
    """Rank must start at 1, never 0 — enforced in code, not left to the
    prompt alone (a model can still return 0 despite being told not to).
    A sub-1 value is coerced to None ('not ranked') rather than rejecting
    the whole response, so one malformed field doesn't waste a whole
    analysis/retry."""
    if value is None or value < 1:
        return None
    return value


class MentionedCompetitor(BaseModel):
    name: str
    rank: int | None = None

    @field_validator("rank")
    @classmethod
    def _clamp_rank(cls, v: int | None) -> int | None:
        return _clamp_rank_to_none_below_one(v)


class AnswerAnalysisResult(BaseModel):
    """Structured classification of one EngineAnswer's raw text — the one
    place in this codebase where a semantic AI judgment substitutes for
    deterministic extraction (mention vs recommendation vs warned-against
    isn't reducible to substring matching). evidence_quote is mandatory
    whenever brand_mentioned is true, so every classification stays
    auditable against the actual answer text, never a bare AI assertion."""

    brand_mentioned: bool
    mention_type: str  # one of MENTION_TYPES
    mention_rank: int | None = None
    recommendation_rank: int | None = None
    competitors_mentioned: list[MentionedCompetitor] = Field(default_factory=list)
    evidence_quote: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("mention_rank", "recommendation_rank")
    @classmethod
    def _clamp_ranks(cls, v: int | None) -> int | None:
        return _clamp_rank_to_none_below_one(v)
