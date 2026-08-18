from app.opportunities.detectors import OpportunityDraft
from app.opportunities.scoring import compute_priority_score


def _draft(**overrides) -> OpportunityDraft:
    defaults = dict(
        opportunity_type="google_visibility_gap",
        title="t",
        description="d",
        fingerprint_target="target",
        estimated_impact=0.8,
        confidence=0.7,
        commercial_relevance=0.9,
        google_visibility_gap=0.6,
        ai_visibility_gap=0.0,
        competitor_gap=0.5,
        effort_estimate="medium",
    )
    defaults.update(overrides)
    return OpportunityDraft(**defaults)


def test_compute_priority_score_matches_documented_formula():
    draft = _draft()
    breakdown = compute_priority_score(draft)

    # visibility_gap = max(0.6, 0.0) = 0.6
    raw = 0.30 * 0.8 + 0.25 * 0.9 + 0.20 * 0.6 + 0.15 * 0.5 + 0.10 * 0.7
    expected = round(raw * 0.85 * 100, 1)

    assert breakdown.priority_score == expected
    assert breakdown.visibility_gap == 0.6
    assert breakdown.effort_multiplier == 0.85
    assert breakdown.scoring_version == "v1"


def test_lower_effort_yields_higher_score_for_identical_draft():
    low_effort = compute_priority_score(_draft(effort_estimate="low"))
    high_effort = compute_priority_score(_draft(effort_estimate="high"))
    assert low_effort.priority_score > high_effort.priority_score


def test_unknown_effort_estimate_falls_back_to_medium_multiplier():
    unknown = compute_priority_score(_draft(effort_estimate="unknown_value"))
    medium = compute_priority_score(_draft(effort_estimate="medium"))
    assert unknown.priority_score == medium.priority_score


def test_visibility_gap_uses_the_stronger_of_google_or_ai():
    draft = _draft(google_visibility_gap=0.2, ai_visibility_gap=0.9)
    breakdown = compute_priority_score(draft)
    assert breakdown.visibility_gap == 0.9


def test_score_is_bounded_between_zero_and_hundred():
    zero_draft = _draft(
        estimated_impact=0.0, confidence=0.0, commercial_relevance=0.0,
        google_visibility_gap=0.0, ai_visibility_gap=0.0, competitor_gap=0.0,
    )
    max_draft = _draft(
        estimated_impact=1.0, confidence=1.0, commercial_relevance=1.0,
        google_visibility_gap=1.0, ai_visibility_gap=1.0, competitor_gap=1.0, effort_estimate="low",
    )
    assert compute_priority_score(zero_draft).priority_score == 0.0
    assert compute_priority_score(max_draft).priority_score == 100.0
