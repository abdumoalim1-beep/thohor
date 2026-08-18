import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models.ai_visibility import AIVisibilityObservation


@dataclass
class AIVisibilityMetrics:
    total_observations: int
    mention_rate: float
    intent_coverage: float
    citation_rate: float
    stability: float


def _compute_from_observations(observations: list[AIVisibilityObservation]) -> AIVisibilityMetrics:
    total = len(observations)
    if total == 0:
        return AIVisibilityMetrics(
            total_observations=0, mention_rate=0.0, intent_coverage=0.0, citation_rate=0.0, stability=0.0
        )

    mention_rate = sum(1 for o in observations if o.mentioned) / total

    distinct_intents = {o.intent_id for o in observations}
    mentioned_intents = {o.intent_id for o in observations if o.mentioned}
    intent_coverage = (len(mentioned_intents) / len(distinct_intents)) if distinct_intents else 0.0

    # Citation Rate denominator is answers with ANY citation, not all
    # answers (PRD section 22) — measures "of the answers that cited a
    # source at all, how many cited us."
    has_any_citation = [o for o in observations if o.citations]
    cites_client = [o for o in has_any_citation if o.linked_domains]
    citation_rate = (len(cites_client) / len(has_any_citation)) if has_any_citation else 0.0

    # Stability: for each (intent, prompt, engine, model) group with >1
    # repetition, what fraction of repetitions agreed with the majority
    # mentioned/not-mentioned outcome — averaged across groups.
    groups: dict[tuple, list[bool]] = defaultdict(list)
    for o in observations:
        groups[(o.intent_id, o.prompt_variant_id, o.provider, o.model)].append(o.mentioned)

    stability_scores = []
    for outcomes in groups.values():
        if len(outcomes) < 2:
            continue
        true_count = sum(outcomes)
        majority = max(true_count, len(outcomes) - true_count)
        stability_scores.append(majority / len(outcomes))
    stability = (sum(stability_scores) / len(stability_scores)) if stability_scores else 1.0

    return AIVisibilityMetrics(
        total_observations=total,
        mention_rate=mention_rate,
        intent_coverage=intent_coverage,
        citation_rate=citation_rate,
        stability=stability,
    )


def compute_ai_visibility_metrics(session: Session, research_run_id: uuid.UUID) -> AIVisibilityMetrics:
    """V1 scope (PRD section 22): Mention Rate, Intent Coverage, Citation
    Rate, Stability. Competitive Share of Voice and a precise Top
    Recommendation Rate are deferred (Group D / later refinement) — see the
    Group C plan's design decision #8.
    """
    observations = session.exec(
        select(AIVisibilityObservation).where(AIVisibilityObservation.research_run_id == research_run_id)
    ).all()
    return _compute_from_observations(observations)


def compute_ai_visibility_metrics_by_surface(
    session: Session, research_run_id: uuid.UUID
) -> dict[str, AIVisibilityMetrics]:
    """Same metrics, split per surface (Part F.5-9) — 'surface' falls back
    to provider for pre-F.5 rows that never got backfilled a surface."""
    observations = session.exec(
        select(AIVisibilityObservation).where(AIVisibilityObservation.research_run_id == research_run_id)
    ).all()
    by_surface: dict[str, list[AIVisibilityObservation]] = defaultdict(list)
    for o in observations:
        by_surface[o.surface or o.provider].append(o)
    return {surface: _compute_from_observations(obs) for surface, obs in by_surface.items()}
