import uuid
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.core.domain import is_synthetic_test_domain
from app.core.urls import normalize_hostname
from app.models.ai_visibility import AIVisibilityObservation
from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.serp import SerpObservation


def _derive_display_name(domain: str) -> str:
    """domain.tld -> title-cased first label, same heuristic already used
    for our own store's fallback brand name (store_intelligence.py's
    _ensure_fallback_brand). Part G-B6 finding: name used to equal domain
    verbatim, so app.ai_visibility.visibility_engine.detect_competitors_mentioned
    was matching a bare hostname string ('amazon.sa') against natural AI
    prose — which essentially never contains that exact string — instead of
    a name a model would actually write ('Amazon'). This only helps the
    Latin-script/English-brand-name case; a domain carries no deterministic
    path to an Arabic transliteration ('أمازون'), which stays a genuine,
    documented limitation of substring matching without AI/curated data."""
    bare = domain.removeprefix("www.").split(".")[0]
    return bare.replace("-", " ").title() or domain


def get_or_create_competitor(
    session: Session,
    *,
    store_id: uuid.UUID,
    domain: str,
    competitor_type: CompetitorType,
    research_run_id: uuid.UUID,
    name: str | None = None,
) -> Competitor:
    """First-seen type wins: if a domain already surfaced via one surface
    (e.g. SERP) and now also shows up via another (AI citation), it keeps
    its original competitor_type — a documented V1 simplification (Group D
    design decision #3), not a bug.

    `name` lets a caller with a real known display name (Phase 4's identity-
    based discovery gets an actual brand name from web search) use it
    instead of the domain-derived fallback — only applies on first creation,
    same as competitor_type."""
    existing = session.exec(
        select(Competitor).where(Competitor.store_id == store_id).where(Competitor.domain == domain)
    ).first()
    if existing is not None:
        return existing

    competitor = Competitor(
        store_id=store_id,
        domain=domain,
        name=name or _derive_display_name(domain),
        competitor_type=competitor_type,
        first_seen_research_run_id=research_run_id,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)
    return competitor


def mine_serp_competitors(
    session: Session, store_id: uuid.UUID, store_url: str, research_run_id: uuid.UUID
) -> list[CompetitorRelationship]:
    """SERP half of discovery — mines serp_observations.results (Group B),
    no new network calls, no new cost. Split out from the AI-visibility half
    (Part G-B5) so it can run once, early, right after the serp_batch fixed
    phase — before ai_visibility_batch runs — instead of only later as the
    iterative loop's seed task. Relationships are immutable/append-only
    (never updated), so this must run exactly once per run; calling it a
    second time would double every SERP relationship, not just refresh it."""
    client_hostname = normalize_hostname(urlparse(store_url).hostname or "")
    relationships: list[CompetitorRelationship] = []

    serp_observations = session.exec(
        select(SerpObservation).where(SerpObservation.research_run_id == research_run_id)
    ).all()
    for observation in serp_observations:
        for result in observation.results:
            domain = result.get("domain")
            if not domain:
                continue
            normalized = normalize_hostname(domain)
            # Part R7 — never persist a reserved test/example domain as a
            # real Competitor, regardless of how it reached this SERP
            # result (a genuine MockSearchProvider run, or ReplaySearchProvider
            # unknowingly replaying old mock-sourced serp_observations).
            if normalized == client_hostname or is_synthetic_test_domain(normalized):
                continue

            competitor = get_or_create_competitor(
                session,
                store_id=store_id,
                domain=normalized,
                competitor_type=CompetitorType.search_competitor,
                research_run_id=research_run_id,
            )
            relationship = CompetitorRelationship(
                competitor_id=competitor.id,
                intent_id=observation.intent_id,
                stable_intent_id=observation.stable_intent_id,
                research_run_id=research_run_id,
                source=RelationshipSource.serp,
                rank_or_position=result.get("rank"),
            )
            session.add(relationship)
            session.commit()
            session.refresh(relationship)
            relationships.append(relationship)

    return relationships


def mine_ai_visibility_competitors(
    session: Session, store_id: uuid.UUID, store_url: str, research_run_id: uuid.UUID
) -> list[CompetitorRelationship]:
    """AI-visibility half of discovery — mines ai_visibility_observations
    (Group C), no new network calls, no new cost.

    Part G-B5 fix: previously this only read `observation.citations` (URLs
    extracted from the AI's raw text via regex) — but no AI surface has
    search grounding enabled in this project (a deliberate V1 scope
    decision, Part C #4), so a plain chat completion almost never contains
    a clickable URL. `observation.competitors_mentioned` (brand/domain names
    matched deterministically against already-known Competitor rows —
    app.ai_visibility.visibility_engine.detect_competitors_mentioned) was
    being collected and persisted this whole time but never mined into a
    CompetitorRelationship — dead data. This is why detect_ai_citation_gap_
    opportunities (app.opportunities.detectors) almost never fired: its
    precondition is 'a competitor was cited for this intent', which was
    only ever checked against the empty `citations` signal."""
    client_hostname = normalize_hostname(urlparse(store_url).hostname or "")
    relationships: list[CompetitorRelationship] = []

    ai_observations = session.exec(
        select(AIVisibilityObservation).where(AIVisibilityObservation.research_run_id == research_run_id)
    ).all()
    for observation in ai_observations:
        domains_this_observation: dict[str, int | None] = {}
        for position, url in enumerate(observation.citations, start=1):
            hostname = urlparse(url).hostname
            if not hostname:
                continue
            normalized = normalize_hostname(hostname)
            if normalized == client_hostname or normalized in domains_this_observation or is_synthetic_test_domain(normalized):
                continue
            domains_this_observation[normalized] = position
        for domain in observation.competitors_mentioned:
            normalized = normalize_hostname(domain)
            if normalized == client_hostname or normalized in domains_this_observation or is_synthetic_test_domain(normalized):
                continue
            domains_this_observation[normalized] = None

        for normalized, position in domains_this_observation.items():
            competitor = get_or_create_competitor(
                session,
                store_id=store_id,
                domain=normalized,
                competitor_type=CompetitorType.ai_recommendation_competitor,
                research_run_id=research_run_id,
            )
            relationship = CompetitorRelationship(
                competitor_id=competitor.id,
                intent_id=observation.intent_id,
                stable_intent_id=observation.stable_intent_id,
                research_run_id=research_run_id,
                source=RelationshipSource.ai_visibility,
                rank_or_position=position,
            )
            session.add(relationship)
            session.commit()
            session.refresh(relationship)
            relationships.append(relationship)

    return relationships


def run_competitor_discovery_agent(
    *,
    session: Session,
    store_id: uuid.UUID,
    store_url: str,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
) -> list[CompetitorRelationship]:
    """Combined SERP + AI-visibility mining in one call — kept for callers
    that want both halves at once (tests, and anywhere that hasn't already
    run mine_serp_competitors earlier in the pipeline). The orchestrator
    itself calls the two halves separately at different pipeline points
    (Part G-B5) — see mine_serp_competitors/mine_ai_visibility_competitors."""
    serp_relationships = mine_serp_competitors(session, store_id, store_url, research_run_id)
    ai_relationships = mine_ai_visibility_competitors(session, store_id, store_url, research_run_id)
    return serp_relationships + ai_relationships
