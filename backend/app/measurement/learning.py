from dataclasses import dataclass

from sqlmodel import Session, select

from app.measurement.impact import compute_recommendation_impact
from app.models.measurement import MeasurementBaseline, MeasurementSnapshot
from app.models.opportunity import Opportunity
from app.models.recommendation import Recommendation, RecommendationStatus

TERMINAL_STATUSES = (
    RecommendationStatus.successful,
    RecommendationStatus.partial,
    RecommendationStatus.no_detectable_impact,
    RecommendationStatus.regressed,
)


@dataclass
class RecommendationTypeStats:
    sample_size: int
    success_rate: float | None
    avg_impact: float | None
    avg_time_to_impact_days: float | None


def compute_recommendation_type_stats(
    session: Session, opportunity_type: str | None = None
) -> RecommendationTypeStats:
    """No ML — just proves the data model captured by F0-F5 is already
    enough to learn from later (Group F6): pulls every recommendation that
    reached a terminal outcome (across all stores) and aggregates success
    rate / average observed impact / average time-to-impact. A future
    real learning system would consume the exact same tables."""
    query = select(Recommendation).where(Recommendation.status.in_(TERMINAL_STATUSES))  # type: ignore[attr-defined]
    recommendations = session.exec(query).all()

    if opportunity_type is not None:
        opportunity_ids = {
            o.id for o in session.exec(select(Opportunity).where(Opportunity.opportunity_type == opportunity_type)).all()
        }
        recommendations = [r for r in recommendations if r.opportunity_id in opportunity_ids]

    if not recommendations:
        return RecommendationTypeStats(sample_size=0, success_rate=None, avg_impact=None, avg_time_to_impact_days=None)

    successes = sum(1 for r in recommendations if r.status == RecommendationStatus.successful)
    impacts: list[float] = []
    time_to_impact_days: list[float] = []

    for recommendation in recommendations:
        baseline = session.exec(
            select(MeasurementBaseline).where(MeasurementBaseline.recommendation_id == recommendation.id)
        ).first()
        if baseline is None:
            continue
        latest_snapshot = session.exec(
            select(MeasurementSnapshot)
            .where(MeasurementSnapshot.recommendation_id == recommendation.id)
            .order_by(MeasurementSnapshot.captured_at.desc())  # type: ignore[arg-type]
        ).first()
        if latest_snapshot is None:
            continue

        impact = compute_recommendation_impact(baseline, latest_snapshot)
        deltas = [d for d in (impact.google_visibility_delta, impact.ai_visibility_delta) if d is not None]
        if deltas:
            impacts.append(max(deltas))

        elapsed = (latest_snapshot.captured_at - baseline.captured_at).total_seconds() / 86400
        time_to_impact_days.append(elapsed)

    return RecommendationTypeStats(
        sample_size=len(recommendations),
        success_rate=successes / len(recommendations),
        avg_impact=(sum(impacts) / len(impacts)) if impacts else None,
        avg_time_to_impact_days=(sum(time_to_impact_days) / len(time_to_impact_days)) if time_to_impact_days else None,
    )
