import re
import uuid

from sqlmodel import Session, select

from app.core.urls import normalize_hostname
from app.models.competitor import Competitor, CompetitorRelationship, RelationshipSource
from app.models.research_task import TaskType
from app.schemas.research_planning import NewTaskSuggestion

ID_TAG_PATTERN = re.compile(r"id=([0-9a-fA-F-]{36})")


def resolve_task_input(
    session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID, suggestion: NewTaskSuggestion
) -> dict | None:
    """Turns a Planner suggestion's free-text `target` into the structured
    `input` dict the matching Executor worker expects. Returns None when
    the target can't be resolved (e.g. the model hallucinated a domain/id
    not actually in the digest it was given) — the Orchestrator drops such
    suggestions rather than creating a task that would just fail (Group D2
    design decision #4: Orchestrator decides what actually runs)."""
    if suggestion.task_type in (TaskType.competitor_deep_dive, TaskType.page_compare):
        domain = normalize_hostname(suggestion.target.strip())
        competitor = session.exec(
            select(Competitor).where(Competitor.store_id == store_id).where(Competitor.domain == domain)
        ).first()
        if competitor is None:
            return None

        best_relationship = session.exec(
            select(CompetitorRelationship)
            .where(CompetitorRelationship.research_run_id == research_run_id)
            .where(CompetitorRelationship.competitor_id == competitor.id)
            .where(CompetitorRelationship.source == RelationshipSource.serp)
            .order_by(CompetitorRelationship.rank_or_position.asc())  # type: ignore[union-attr]
        ).first()
        if best_relationship is None:
            return None

        return {"competitor_id": str(competitor.id), "intent_id": str(best_relationship.intent_id)}

    if suggestion.task_type in (
        TaskType.query_expansion,
        TaskType.search_google,
        TaskType.ai_visibility_chatgpt,
        TaskType.ai_visibility_gemini,
        TaskType.ai_visibility_claude,
    ):
        match = ID_TAG_PATTERN.search(suggestion.target)
        return {"intent_id": match.group(1)} if match else None

    if suggestion.task_type in (TaskType.validate_finding, TaskType.validate_cross_surface_finding):
        match = ID_TAG_PATTERN.search(suggestion.target)
        return {"finding_id": match.group(1)} if match else None

    return None
