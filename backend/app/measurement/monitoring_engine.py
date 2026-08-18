import uuid

from sqlmodel import Session, select
from sqlalchemy.orm import defer

from app.ai_visibility.surfaces import AISurface
from app.core.evaluation_mode import EvaluationMode
from app.measurement.baseline import measure_visibility_for_intents
from app.measurement.control_set import remeasure_control_set
from app.measurement.implementation_detection import detect_implementation
from app.measurement.impact import compute_recommendation_impact
from app.measurement.outcome import classify_outcome
from app.models.base import utcnow
from app.models.measurement import MeasurementBaseline, MeasurementSnapshot
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.store import Store
from app.providers.ai.router import ModelRouter
from app.providers.search.base import SearchProvider

MONITORING_ELIGIBLE_STATUSES = (RecommendationStatus.implemented, RecommendationStatus.monitoring)


async def run_monitoring_pass(
    session: Session,
    store: Store,
    research_run_id: uuid.UUID,
    *,
    search_provider: SearchProvider | None = None,
    router: ModelRouter | None = None,
    ai_surfaces: list[AISurface] | None = None,
    agent_run_id: uuid.UUID | None = None,
    evaluation_mode: EvaluationMode = EvaluationMode.live,
) -> dict:
    """Group F3/F4/F5 combined: for every recommendation still awaiting
    implementation, tries automatic detection (Part F1); for every
    recommendation already implemented/monitoring, actively re-issues its
    exact baseline Control Set queries/prompts (Part F.5-11 — this cannot
    rely on the current run's Discovery-regenerated intents happening to
    overlap, they usually don't) and re-classifies the outcome (Part F5).
    search_provider/router/ai_surfaces are optional so this stays callable
    (as a passive read-only pass) without live providers, e.g. in tests
    that only exercise the classification logic.
    """
    pending_implementation = session.exec(
        select(Recommendation)
        .options(defer(Recommendation.page_id), defer(Recommendation.product_id))
        .where(Recommendation.store_id == store.id)
        .where(Recommendation.status.in_([RecommendationStatus.new, RecommendationStatus.planned, RecommendationStatus.in_progress]))  # type: ignore[attr-defined]
    ).all()
    auto_detected = 0
    for recommendation in pending_implementation:
        change_set = detect_implementation(session, recommendation)
        if change_set is not None and change_set.has_meaningful_change():
            auto_detected += 1

    monitored = session.exec(
        select(Recommendation)
        .options(defer(Recommendation.page_id), defer(Recommendation.product_id))
        .where(Recommendation.store_id == store.id)
        .where(Recommendation.status.in_(MONITORING_ELIGIBLE_STATUSES))  # type: ignore[attr-defined]
    ).all()

    snapshots_taken = 0
    outcomes_classified = 0
    for recommendation in monitored:
        if recommendation.status == RecommendationStatus.implemented:
            recommendation.status = RecommendationStatus.monitoring
            recommendation.updated_at = utcnow()
            session.add(recommendation)
            session.commit()

        baseline = session.exec(
            select(MeasurementBaseline).where(MeasurementBaseline.recommendation_id == recommendation.id)
        ).first()
        if baseline is None:
            continue

        if search_provider is not None and router is not None:
            await remeasure_control_set(
                session=session, search_provider=search_provider, router=router, store=store,
                recommendation_id=recommendation.id, research_run_id=research_run_id, agent_run_id=agent_run_id,
                ai_surfaces=ai_surfaces or [], evaluation_mode=evaluation_mode,
            )

        _, _, google_visibility, ai_visibility = measure_visibility_for_intents(
            session, research_run_id, recommendation.target_intents
        )
        if google_visibility is None and ai_visibility is None:
            continue  # these intents weren't re-measured this run — nothing new to compare

        snapshot = MeasurementSnapshot(
            recommendation_id=recommendation.id,
            research_run_id=research_run_id,
            google_visibility=google_visibility,
            ai_visibility=ai_visibility,
        )
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)
        snapshots_taken += 1

        impact = compute_recommendation_impact(baseline, snapshot)
        outcome = classify_outcome(impact)
        recommendation.status = outcome
        recommendation.updated_at = utcnow()
        session.add(recommendation)
        session.commit()
        outcomes_classified += 1

    return {
        "recommendations_checked_for_implementation": len(pending_implementation),
        "implementations_auto_detected": auto_detected,
        "recommendations_monitored": len(monitored),
        "snapshots_taken": snapshots_taken,
        "outcomes_classified": outcomes_classified,
    }
