from app.measurement.impact import ImpactRecord, compute_recommendation_impact
from app.measurement.outcome import classify_outcome
from app.models.measurement import MeasurementBaseline, MeasurementSnapshot
from app.models.recommendation import RecommendationStatus


def _impact(google_delta=None, ai_delta=None) -> ImpactRecord:
    return ImpactRecord(
        google_visibility_before=0.2, google_visibility_after=None,
        ai_visibility_before=0.1, ai_visibility_after=None,
        google_visibility_delta=google_delta, ai_visibility_delta=ai_delta,
    )


def test_compute_recommendation_impact_computes_deltas():
    baseline = MeasurementBaseline(recommendation_id="00000000-0000-0000-0000-000000000000", research_run_id="00000000-0000-0000-0000-000000000000", google_visibility=0.2, ai_visibility=0.1)
    snapshot = MeasurementSnapshot(recommendation_id="00000000-0000-0000-0000-000000000000", research_run_id="00000000-0000-0000-0000-000000000000", google_visibility=0.4, ai_visibility=0.05)

    impact = compute_recommendation_impact(baseline, snapshot)

    assert impact.google_visibility_delta == 0.4 - 0.2
    assert round(impact.ai_visibility_delta, 10) == round(0.05 - 0.1, 10)


def test_compute_recommendation_impact_handles_missing_values():
    baseline = MeasurementBaseline(recommendation_id="00000000-0000-0000-0000-000000000000", research_run_id="00000000-0000-0000-0000-000000000000", google_visibility=None, ai_visibility=0.1)
    snapshot = MeasurementSnapshot(recommendation_id="00000000-0000-0000-0000-000000000000", research_run_id="00000000-0000-0000-0000-000000000000", google_visibility=0.4, ai_visibility=0.15)

    impact = compute_recommendation_impact(baseline, snapshot)

    assert impact.google_visibility_delta is None
    assert impact.ai_visibility_delta is not None


def test_classify_outcome_successful_when_large_improvement():
    assert classify_outcome(_impact(google_delta=0.2)) == RecommendationStatus.successful


def test_classify_outcome_regressed_when_large_decline():
    assert classify_outcome(_impact(google_delta=-0.2)) == RecommendationStatus.regressed


def test_classify_outcome_partial_when_small_improvement():
    assert classify_outcome(_impact(google_delta=0.05)) == RecommendationStatus.partial


def test_classify_outcome_no_detectable_impact_when_flat():
    assert classify_outcome(_impact(google_delta=0.0, ai_delta=0.0)) == RecommendationStatus.no_detectable_impact


def test_classify_outcome_stays_monitoring_when_no_data():
    assert classify_outcome(_impact()) == RecommendationStatus.monitoring


def test_classify_outcome_uses_best_signal_across_google_and_ai():
    # AI regressed but Google improved strongly -> still counts as successful
    assert classify_outcome(_impact(google_delta=0.3, ai_delta=-0.2)) == RecommendationStatus.successful
