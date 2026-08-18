import uuid

from sqlmodel import Session, select

from app.models.ai_visibility import AIVisibilityObservation
from app.models.catalog import Page
from app.models.measurement import MeasurementBaseline
from app.models.observation import PageObservation
from app.models.recommendation import Recommendation
from app.models.serp import SerpObservation

WEAK_RANK_THRESHOLD = 10


def _capture_page_metrics(session: Session, store_id: uuid.UUID, target_page: str | None) -> dict:
    """None of the Group E V1 detectors populate affected_pages yet (Part
    E1 design decision #3), so target_page is normally None — this stays a
    no-op today but is what a future page-level detector, or a manually
    set target_page, would need for Part F1's automatic implementation
    detection to have a real 'before' snapshot to diff against."""
    if not target_page:
        return {}
    page = session.exec(select(Page).where(Page.store_id == store_id).where(Page.url == target_page)).first()
    if page is None:
        return {}
    observation = session.exec(
        select(PageObservation)
        .where(PageObservation.page_id == page.id)
        .order_by(PageObservation.created_at.desc())  # type: ignore[arg-type]
    ).first()
    return observation.normalized_extraction if observation else {}


def measure_visibility_for_intents(
    session: Session, research_run_id: uuid.UUID, target_stable_intents: list[str]
) -> tuple[list[dict], list[dict], float | None, float | None]:
    """Reads whatever SERP/AI-visibility observations already exist in the
    given research_run for these specific *stable* intents (Part F.5-0) —
    never issues a new search/AI call itself. Shared by baseline capture
    (Part F0) and monitoring snapshots (Part F3): the Control Set is
    'whichever of these intents this run naturally re-measured', not a
    forced fresh query — zero extra cost, and consistent with 'no Discovery
    queries used for historical performance measurement'.

    Filtering by stable_intent_id (not intent_id) is what makes this work
    across different research_runs: every run creates brand-new Intent rows
    with new UUIDs, but they carry forward the same stable_intent_id for
    the same real-world question, so a later run's fresh observations still
    match a Recommendation's target_intents captured at baseline time.
    """
    target_queries: list[dict] = []
    target_prompts: list[dict] = []
    rank_scores: list[float] = []
    mention_scores: list[float] = []

    for stable_intent_id_str in target_stable_intents:
        stable_intent_id = uuid.UUID(stable_intent_id_str)

        serp_observation = session.exec(
            select(SerpObservation)
            .where(SerpObservation.research_run_id == research_run_id)
            .where(SerpObservation.stable_intent_id == stable_intent_id)
        ).first()
        if serp_observation is not None:
            target_queries.append(
                {
                    "stable_intent_id": stable_intent_id_str,
                    "keyword_id": str(serp_observation.keyword_id),
                    "client_rank": serp_observation.client_rank,
                }
            )
            rank_scores.append(
                1.0
                if serp_observation.client_rank is not None and serp_observation.client_rank <= WEAK_RANK_THRESHOLD
                else 0.0
            )

        ai_observations = session.exec(
            select(AIVisibilityObservation)
            .where(AIVisibilityObservation.research_run_id == research_run_id)
            .where(AIVisibilityObservation.stable_intent_id == stable_intent_id)
        ).all()
        for obs in ai_observations:
            target_prompts.append(
                {
                    "stable_intent_id": stable_intent_id_str,
                    "prompt_variant_id": str(obs.prompt_variant_id),
                    "provider": obs.provider,
                    "model": obs.model,
                }
            )
            mention_scores.append(1.0 if obs.mentioned else 0.0)

    google_visibility = (sum(rank_scores) / len(rank_scores)) if rank_scores else None
    ai_visibility = (sum(mention_scores) / len(mention_scores)) if mention_scores else None
    return target_queries, target_prompts, google_visibility, ai_visibility


def capture_measurement_baseline(
    session: Session, recommendation: Recommendation, research_run_id: uuid.UUID
) -> MeasurementBaseline:
    """Captures the 'before' state exactly once, at the moment a
    Recommendation is first created (Group F design decision #1) — never
    called again for that recommendation afterward, so there is always a
    real before-state to compare against later. recommendation.target_intents
    holds StableIntent ids (Part F.5-0), not run-scoped Intent ids.
    """
    target_queries, target_prompts, google_visibility, ai_visibility = measure_visibility_for_intents(
        session, research_run_id, recommendation.target_intents
    )

    baseline = MeasurementBaseline(
        recommendation_id=recommendation.id,
        research_run_id=research_run_id,
        target_queries=target_queries,
        target_prompts=target_prompts,
        google_visibility=google_visibility,
        ai_visibility=ai_visibility,
        page_metrics=_capture_page_metrics(session, recommendation.store_id, recommendation.target_page),
    )
    session.add(baseline)
    session.commit()
    session.refresh(baseline)
    return baseline
