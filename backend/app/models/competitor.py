import uuid
from enum import Enum

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel


class CompetitorType(str, Enum):
    """Discovery source — HOW this domain first surfaced, not WHAT kind of
    site it is. Deliberately distinct from Competitor.classification (Part
    G-B2), which is the business-relevance taxonomy customers actually see."""

    search_competitor = "search_competitor"
    ai_recommendation_competitor = "ai_recommendation_competitor"
    # Phase 4 — surfaced by resolve_store_identity + discover_competitors'
    # web-search call, independent of any SERP/AI-visibility observation.
    identity_web_search = "identity_web_search"


class RelationshipSource(str, Enum):
    serp = "serp"
    ai_visibility = "ai_visibility"


class Competitor(TimestampedModel, table=True):
    """One row per unique competitor domain per store — mined from
    serp_observations.results and ai_visibility_observations.citations,
    never from a new external data source. competitor_type reflects
    whichever source first surfaced this domain (discovery mechanism —
    unchanged since Group D).

    Part G-B2 adds the business-relevance layer on top: classification is
    what actually gets shown to the store owner (direct_competitor /
    marketplace / publisher / social / video / government / manufacturer /
    retailer / irrelevant / unknown) — a domain appearing in Google is not
    automatically a "competitor" the customer cares about.
    """

    __tablename__ = "competitors"

    store_id: uuid.UUID = Field(foreign_key="stores.id", index=True)
    domain: str = Field(index=True)
    name: str
    competitor_type: CompetitorType
    first_seen_research_run_id: uuid.UUID = Field(foreign_key="research_runs.id")

    # Part G-B2 — business-relevance classification. Plain string (not a
    # Postgres enum), same rationale as opportunity_type: this taxonomy
    # will keep growing (forums, review sites, ...) and every prior group
    # paid a manual-migration tax for closed enums that grew.
    classification: str = Field(default="unknown", index=True)
    relevance_score: float = Field(default=0.0)
    classification_confidence: float = Field(default=0.0)
    discovery_reason: str | None = None
    shared_stable_intents: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))
    evidence_ids: list[str] = Field(default_factory=list, sa_column=Column(PortableJSONB))

    # Phase 4 — plain string, not a Postgres enum (same rationale as
    # `classification`: this vocabulary is closed today but a closed enum
    # here has already cost a manual-migration tax elsewhere in this
    # codebase — see Phase 1's web_search_citation bug). Only identity-based
    # discovery ever sets this away from the default; SERP/AI-visibility-
    # mined competitors have no human-review concept and stay
    # "pending_user_confirmation" forever unless a user acts on them.
    confirmation_status: str = Field(default="pending_user_confirmation", index=True)


class CompetitorRelationship(TimestampedModel, table=True):
    """Links a competitor to a specific intent + the search surface it was
    observed on (SERP rank or an AI visibility citation). Immutable: a new
    observation always inserts a new relationship row, never updates one."""

    __tablename__ = "competitor_relationships"

    competitor_id: uuid.UUID = Field(foreign_key="competitors.id", index=True)
    intent_id: uuid.UUID = Field(foreign_key="intents.id", index=True)
    # Part G-B2 — same reason as every other stable_intent_id addition
    # since Part F.5-0: Intent rows are recreated every research_run, so
    # "this competitor shares N intents with the store" can only be
    # computed correctly across runs via the stable identity, not intent_id.
    stable_intent_id: uuid.UUID | None = Field(default=None, foreign_key="stable_intents.id", index=True)
    research_run_id: uuid.UUID = Field(foreign_key="research_runs.id", index=True)

    source: RelationshipSource
    rank_or_position: int | None = None
