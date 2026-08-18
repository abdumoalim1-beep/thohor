import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models.serp import SerpObservation


@dataclass
class VisibilityMetrics:
    total_intents_measured: int
    ranking_coverage: float
    top3_rate: float
    top10_rate: float
    avg_client_rank: float | None


def compute_visibility_metrics(session: Session, research_run_id: uuid.UUID) -> VisibilityMetrics:
    """Computed on demand from serp_observations — no separate score_snapshots
    table yet (that arrives with the versioned multi-component AI Visibility
    Score in Group C, per PRD section 23)."""
    observations = session.exec(
        select(SerpObservation).where(SerpObservation.research_run_id == research_run_id)
    ).all()

    total = len(observations)
    if total == 0:
        return VisibilityMetrics(
            total_intents_measured=0, ranking_coverage=0.0, top3_rate=0.0, top10_rate=0.0, avg_client_rank=None
        )

    ranked = [o.client_rank for o in observations if o.client_rank is not None]

    return VisibilityMetrics(
        total_intents_measured=total,
        ranking_coverage=len(ranked) / total,
        top3_rate=sum(1 for r in ranked if r <= 3) / total,
        top10_rate=sum(1 for r in ranked if r <= 10) / total,
        avg_client_rank=(sum(ranked) / len(ranked)) if ranked else None,
    )
