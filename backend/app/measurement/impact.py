from dataclasses import dataclass

from app.models.measurement import MeasurementBaseline, MeasurementSnapshot


@dataclass
class ImpactRecord:
    """'Observed impact', never 'guaranteed causation' (Group F design
    decision #4) — a plain before/after delta, computed on demand from
    measurement_baselines + measurement_snapshots, never stored as its own
    row (same philosophy as compute_visibility_metrics/
    compute_competitor_rankings elsewhere in the project)."""

    google_visibility_before: float | None
    google_visibility_after: float | None
    ai_visibility_before: float | None
    ai_visibility_after: float | None
    google_visibility_delta: float | None
    ai_visibility_delta: float | None


def compute_recommendation_impact(baseline: MeasurementBaseline, snapshot: MeasurementSnapshot) -> ImpactRecord:
    google_delta = (
        snapshot.google_visibility - baseline.google_visibility
        if snapshot.google_visibility is not None and baseline.google_visibility is not None
        else None
    )
    ai_delta = (
        snapshot.ai_visibility - baseline.ai_visibility
        if snapshot.ai_visibility is not None and baseline.ai_visibility is not None
        else None
    )
    return ImpactRecord(
        google_visibility_before=baseline.google_visibility,
        google_visibility_after=snapshot.google_visibility,
        ai_visibility_before=baseline.ai_visibility,
        ai_visibility_after=snapshot.ai_visibility,
        google_visibility_delta=google_delta,
        ai_visibility_delta=ai_delta,
    )
