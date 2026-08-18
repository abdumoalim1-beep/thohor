import uuid
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.core.urls import normalize_hostname
from app.models.ai_visibility import AIVisibilityObservation
from app.models.competitor import Competitor
from app.models.serp import SerpObservation
from app.models.stable_intent import StableIntent

GOOGLE_SURFACE = "google"
WEAK_RANK_THRESHOLD = 10


@dataclass
class IntentSurfaceVisibility:
    """Part F.5-9 — 'how visible are we, per surface, for this real-world
    question, versus each competitor'. Google is folded in as just another
    surface (source: SerpObservation, not AIVisibilityObservation) so
    callers get one unified view instead of a separate Google dashboard —
    exactly what Part F.5-13 asks the frontend to avoid."""

    stable_intent_id: uuid.UUID
    topic: str
    store_visibility: dict[str, float] = field(default_factory=dict)  # surface -> 0..1
    competitor_visibility: dict[str, dict[str, float]] = field(default_factory=dict)  # domain -> {surface: 0..1}
    # Part R6 — domain -> Competitor.classification, for every domain that
    # also appears in competitor_visibility. Without this the frontend has
    # no way to tell a real business rival apart from a publisher/
    # marketplace/etc. domain that simply out-ranked the store in the raw
    # SERP/AI results (e.g. Wikipedia answering an informational query).
    competitor_classifications: dict[str, str] = field(default_factory=dict)


def _google_visible(serp_observation: SerpObservation) -> bool:
    return serp_observation.client_rank is not None and serp_observation.client_rank <= WEAK_RANK_THRESHOLD


def _competitor_domains_in_serp_results(serp_observation: SerpObservation) -> set[str]:
    domains = set()
    for result in serp_observation.results[:WEAK_RANK_THRESHOLD]:
        domain = result.get("domain")
        if domain:
            domains.add(normalize_hostname(domain))
    return domains


def compute_cross_surface_visibility(
    session: Session, research_run_id: uuid.UUID
) -> list[IntentSurfaceVisibility]:
    """One row per stable intent that was measured on at least one surface
    this run. Store/competitor visibility per surface is a simple 0..1 rate
    (Google: single query, so effectively 0 or 1; AI surfaces: mention rate
    across whatever prompts/repetitions ran for that intent+surface)."""
    serp_observations = session.exec(
        select(SerpObservation)
        .where(SerpObservation.research_run_id == research_run_id)
        .where(SerpObservation.stable_intent_id.is_not(None))  # type: ignore[union-attr]
    ).all()
    ai_observations = session.exec(
        select(AIVisibilityObservation)
        .where(AIVisibilityObservation.research_run_id == research_run_id)
        .where(AIVisibilityObservation.stable_intent_id.is_not(None))  # type: ignore[union-attr]
    ).all()

    stable_intent_ids = {o.stable_intent_id for o in serp_observations} | {o.stable_intent_id for o in ai_observations}
    if not stable_intent_ids:
        return []

    competitors = session.exec(select(Competitor).where(Competitor.store_id.in_(  # type: ignore[union-attr]
        {o.store_id for o in serp_observations} | {o.store_id for o in ai_observations}
    ))).all()
    competitor_by_domain = {normalize_hostname(c.domain): c for c in competitors}

    results: dict[uuid.UUID, IntentSurfaceVisibility] = {}
    for stable_intent_id in stable_intent_ids:
        stable_intent = session.get(StableIntent, stable_intent_id)
        results[stable_intent_id] = IntentSurfaceVisibility(
            stable_intent_id=stable_intent_id,
            topic=stable_intent.canonical_topic if stable_intent else str(stable_intent_id),
        )

    for obs in serp_observations:
        entry = results[obs.stable_intent_id]
        entry.store_visibility[GOOGLE_SURFACE] = 1.0 if _google_visible(obs) else 0.0
        for domain in _competitor_domains_in_serp_results(obs):
            if domain in competitor_by_domain:
                entry.competitor_visibility.setdefault(domain, {})[GOOGLE_SURFACE] = 1.0
                entry.competitor_classifications[domain] = competitor_by_domain[domain].classification

    ai_groups: dict[tuple[uuid.UUID, str], list[AIVisibilityObservation]] = {}
    for obs in ai_observations:
        ai_groups.setdefault((obs.stable_intent_id, obs.surface or obs.provider), []).append(obs)

    for (stable_intent_id, surface), obs_list in ai_groups.items():
        entry = results[stable_intent_id]
        entry.store_visibility[surface] = sum(1 for o in obs_list if o.mentioned) / len(obs_list)

        mentioned_domains: dict[str, list[bool]] = {}
        for o in obs_list:
            for domain in o.competitors_mentioned:
                mentioned_domains.setdefault(domain, []).append(True)
        for domain, hits in mentioned_domains.items():
            entry.competitor_visibility.setdefault(domain, {})[surface] = len(hits) / len(obs_list)
            competitor = competitor_by_domain.get(normalize_hostname(domain))
            if competitor is not None:
                entry.competitor_classifications[domain] = competitor.classification

    return list(results.values())
