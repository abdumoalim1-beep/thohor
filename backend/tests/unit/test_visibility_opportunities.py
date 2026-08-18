"""SIGNUP-4 — derive_top_opportunities: exactly the top-2 highest-priority
real findings, never padded with generic unsupported recommendations, and
every returned opportunity carries evidence traceable to the metrics that
produced it."""

from app.ai_visibility.visibility_metrics_v2 import CompetitorVisibilitySummary, VisibilityMetricsV2
from app.ai_visibility.visibility_opportunities import derive_top_opportunities


def _metrics(**overrides) -> VisibilityMetricsV2:
    base = dict(
        successful_answers=20, mention_rate=0.5, recommendation_rate=0.4, avg_recommendation_rank=2.0,
        top_3_rate=0.3, share_of_voice=0.5, citation_rate=0.6, top_competitor=None, top_competitor_mentions=0,
        total_searches=20, mentioned_count=10, avg_mention_rank=2.0, top3_count=6,
    )
    base.update(overrides)
    return VisibilityMetricsV2(**base)


def test_no_findings_when_metrics_are_all_healthy():
    metrics = _metrics()
    assert derive_top_opportunities(metrics, []) == []


def test_low_visibility_is_detected_with_real_evidence():
    metrics = _metrics(successful_answers=30, mentioned_count=2, mention_rate=0.0666, recommendation_rate=0.0, citation_rate=None)
    opportunities = derive_top_opportunities(metrics, [])
    assert len(opportunities) == 1
    assert "غائبة" in opportunities[0].title
    assert "2" in opportunities[0].evidence and "30" in opportunities[0].evidence


def test_small_sample_never_triggers_a_finding():
    """Below MIN_SAMPLE_FOR_CONFIDENT_FINDING — even a 0% mention rate must
    not produce a confident-sounding claim from too little data."""
    metrics = _metrics(successful_answers=3, mentioned_count=0, mention_rate=0.0, citation_rate=0.0)
    assert derive_top_opportunities(metrics, []) == []


def test_returns_at_most_two_even_with_more_real_candidates():
    metrics = _metrics(
        successful_answers=30, mentioned_count=10, mention_rate=0.3, recommendation_rate=0.05, citation_rate=0.1,
    )
    competitors = [
        CompetitorVisibilitySummary(name="منافس قوي", domain="strong.com", appearances=20, appearance_rate=0.67, avg_rank=1.0, ahead_of_client=True),
    ]
    opportunities = derive_top_opportunities(metrics, competitors, limit=2)
    assert len(opportunities) == 2


def test_competitor_ahead_evidence_names_the_real_competitor():
    metrics = _metrics(successful_answers=25, mentioned_count=5, mention_rate=0.2, avg_mention_rank=4.0, recommendation_rate=0.15)
    competitors = [
        CompetitorVisibilitySummary(name="أزهار جود", domain="azhar.com", appearances=15, appearance_rate=0.6, avg_rank=1.5, ahead_of_client=True),
    ]
    opportunities = derive_top_opportunities(metrics, competitors, limit=2)
    assert any("أزهار جود" in o.evidence for o in opportunities)
