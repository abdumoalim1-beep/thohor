from dataclasses import dataclass

from app.opportunities.detectors import OpportunityDraft

SCORING_VERSION = "v1"

EFFORT_MULTIPLIERS = {"low": 1.0, "medium": 0.85, "high": 0.7}

IMPACT_WEIGHT = 0.30
COMMERCIAL_RELEVANCE_WEIGHT = 0.25
VISIBILITY_GAP_WEIGHT = 0.20
COMPETITOR_GAP_WEIGHT = 0.15
CONFIDENCE_WEIGHT = 0.10


@dataclass
class ScoreBreakdown:
    priority_score: float
    impact: float
    confidence: float
    commercial_relevance: float
    visibility_gap: float
    competitor_gap: float
    effort_estimate: str
    effort_multiplier: float
    scoring_version: str = SCORING_VERSION


def compute_priority_score(draft: OpportunityDraft) -> ScoreBreakdown:
    """Deterministic, versioned — never an LLM judgment call (Group E design
    decision #4). Weights are config, not sacred; scoring_version is stored
    on every persisted Opportunity so a future weight change never silently
    reinterprets old scores."""
    visibility_gap = max(draft.google_visibility_gap, draft.ai_visibility_gap)
    raw = (
        IMPACT_WEIGHT * draft.estimated_impact
        + COMMERCIAL_RELEVANCE_WEIGHT * draft.commercial_relevance
        + VISIBILITY_GAP_WEIGHT * visibility_gap
        + COMPETITOR_GAP_WEIGHT * draft.competitor_gap
        + CONFIDENCE_WEIGHT * draft.confidence
    )
    effort_multiplier = EFFORT_MULTIPLIERS.get(draft.effort_estimate, EFFORT_MULTIPLIERS["medium"])
    priority_score = round(raw * effort_multiplier * 100, 1)

    return ScoreBreakdown(
        priority_score=priority_score,
        impact=draft.estimated_impact,
        confidence=draft.confidence,
        commercial_relevance=draft.commercial_relevance,
        visibility_gap=visibility_gap,
        competitor_gap=draft.competitor_gap,
        effort_estimate=draft.effort_estimate,
        effort_multiplier=effort_multiplier,
    )
