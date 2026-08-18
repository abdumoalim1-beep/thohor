from sqlmodel import Session, select

from app.measurement.change_detection import ChangeSet, compare_page_states
from app.models.base import utcnow
from app.models.catalog import Page
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.measurement import MeasurementBaseline
from app.models.observation import PageObservation
from app.models.recommendation import Recommendation, RecommendationStatus


def detect_implementation(session: Session, recommendation: Recommendation) -> ChangeSet | None:
    """Method 1 of 3 (Part F1): automatic detection via page re-crawl diff.
    Methods 2 (manual 'تم التنفيذ' confirmation) and 3 (URL proof) are just
    the existing PATCH /recommendations/{id}/status accepting
    implementation_url — no separate code path needed for those.

    Returns None when there's nothing to compare (no target_page, no
    baseline, or the page hasn't been crawled again yet) — not a
    'no change' verdict, just 'can't tell yet'.
    """
    if not recommendation.target_page:
        return None

    baseline = session.exec(
        select(MeasurementBaseline).where(MeasurementBaseline.recommendation_id == recommendation.id)
    ).first()
    if baseline is None:
        return None

    page = session.exec(
        select(Page).where(Page.store_id == recommendation.store_id).where(Page.url == recommendation.target_page)
    ).first()
    if page is None:
        return None

    latest_observation = session.exec(
        select(PageObservation)
        .where(PageObservation.page_id == page.id)
        .order_by(PageObservation.created_at.desc())  # type: ignore[arg-type]
    ).first()
    if latest_observation is None:
        return None

    change_set = compare_page_states(baseline.page_metrics or None, latest_observation.normalized_extraction or {})

    if change_set.has_meaningful_change() and recommendation.status in (
        RecommendationStatus.new,
        RecommendationStatus.planned,
        RecommendationStatus.in_progress,
    ):
        recommendation.status = RecommendationStatus.implemented
        if recommendation.implemented_at is None:
            recommendation.implemented_at = utcnow()
        recommendation.updated_at = utcnow()
        session.add(recommendation)
        session.commit()

        session.add(
            Evidence(
                store_id=recommendation.store_id,
                research_run_id=latest_observation.research_run_id,
                source_type=EvidenceSourceType.implementation_change_detection,
                source_id=latest_observation.id,
                confidence=0.7,
                summary=f"تغيّر تلقائي مكتشف في {recommendation.target_page}",
            )
        )
        session.commit()

    return change_set
