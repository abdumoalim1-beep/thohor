from app.measurement.impact import ImpactRecord
from app.models.recommendation import RecommendationStatus

SUCCESS_THRESHOLD = 0.15
REGRESSION_THRESHOLD = -0.10


def classify_outcome(impact: ImpactRecord) -> RecommendationStatus:
    """Deterministic thresholds (Group F5) — no AI judgment call. Uses
    whichever signal (Google or AI visibility) moved the most in either
    direction, since a recommendation can legitimately move just one of
    the two."""
    deltas = [d for d in (impact.google_visibility_delta, impact.ai_visibility_delta) if d is not None]
    if not deltas:
        return RecommendationStatus.monitoring  # insufficient_data isn't a status value; stays in monitoring until a snapshot lands

    best = max(deltas)
    worst = min(deltas)

    if best >= SUCCESS_THRESHOLD:
        return RecommendationStatus.successful
    if worst <= REGRESSION_THRESHOLD:
        return RecommendationStatus.regressed
    if best > 0:
        return RecommendationStatus.partial
    return RecommendationStatus.no_detectable_impact
