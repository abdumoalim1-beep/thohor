import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource


@dataclass
class CompetitorRanking:
    competitor_id: uuid.UUID
    domain: str
    name: str
    competitor_type: CompetitorType
    serp_appearances: int
    avg_serp_rank: float | None
    ai_citation_count: int
    classification: str
    relevance_score: float
    classification_confidence: float
    discovery_reason: str | None
    shared_stable_intents_count: int


def compute_competitor_rankings(session: Session, research_run_id: uuid.UUID) -> list[CompetitorRanking]:
    """Computed on demand from competitor_relationships — same philosophy as
    serp/metrics.py and ai_visibility/metrics.py (no separate stored
    snapshot table). Strongest competitor first: most total appearances
    across both surfaces, ties broken by the better (lower) average SERP
    rank."""
    relationships = session.exec(
        select(CompetitorRelationship).where(CompetitorRelationship.research_run_id == research_run_id)
    ).all()

    by_competitor: dict[uuid.UUID, list[CompetitorRelationship]] = {}
    for relationship in relationships:
        by_competitor.setdefault(relationship.competitor_id, []).append(relationship)

    rankings: list[CompetitorRanking] = []
    for competitor_id, rels in by_competitor.items():
        competitor = session.get(Competitor, competitor_id)
        if competitor is None:
            continue

        serp_ranks = [
            r.rank_or_position for r in rels if r.source == RelationshipSource.serp and r.rank_or_position is not None
        ]
        serp_appearances = sum(1 for r in rels if r.source == RelationshipSource.serp)
        ai_citation_count = sum(1 for r in rels if r.source == RelationshipSource.ai_visibility)

        rankings.append(
            CompetitorRanking(
                competitor_id=competitor.id,
                domain=competitor.domain,
                name=competitor.name,
                competitor_type=competitor.competitor_type,
                serp_appearances=serp_appearances,
                avg_serp_rank=(sum(serp_ranks) / len(serp_ranks)) if serp_ranks else None,
                ai_citation_count=ai_citation_count,
                classification=competitor.classification,
                relevance_score=competitor.relevance_score,
                classification_confidence=competitor.classification_confidence,
                discovery_reason=competitor.discovery_reason,
                shared_stable_intents_count=len(competitor.shared_stable_intents),
            )
        )

    # Business relevance first (direct competitors surface before generic
    # visibility entities), then strength within that tier (Part G-B2 —
    # "قوة المنافس بناءً على تكرار ظهوره عبر عدة Stable Intents").
    rankings.sort(
        key=lambda r: (
            0 if r.classification == "direct_competitor" else 1,
            -r.relevance_score,
            -(r.serp_appearances + r.ai_citation_count),
            r.avg_serp_rank if r.avg_serp_rank is not None else float("inf"),
        )
    )
    return rankings
