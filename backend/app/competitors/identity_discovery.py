"""Identity-based competitor discovery — Phase 4. Complements the existing
SERP/AI-visibility mining (app.competitors.discovery_engine): those need a
completed research run's SERP/AI-visibility observations to mine competitors
from citations, so a first-ever baseline run on a blocked/thin-crawl store
has nothing to mine yet. This asks a web-search-enabled AI call directly for
named competitors instead, so suggestions exist even before any SERP/AI-
visibility data does — reusing the exact same exclusion (classify_known_
domain) and get-or-create (get_or_create_competitor) machinery as the
existing engine, never a second, divergent implementation of "is this
domain even a real competitor."
"""

import asyncio
import uuid
from urllib.parse import urlparse

from sqlmodel import Session

from app.competitors.classification import classify_known_domain
from app.competitors.discovery_engine import get_or_create_competitor
from app.core.domain import is_synthetic_test_domain
from app.core.urls import normalize_hostname
from app.models.competitor import Competitor, CompetitorType
from app.models.evidence import Evidence, EvidenceSourceType
from app.prompts.competitor_discovery import COMPETITOR_DISCOVERY_PROMPT
from app.providers.ai.base import AIProviderError
from app.providers.ai.router import ModelRouter
from app.schemas.competitor_discovery import CompetitorDiscoveryResult
from app.schemas.store_identity import StoreIdentity

# A suggestion needs no human review before it's treated as a real
# competitor everywhere Competitor.classification/relevance_score already
# get read — either two independent sources agree, or one source came with
# high stated confidence.
AUTO_CONFIRM_MIN_SOURCES = 2
AUTO_CONFIRM_MIN_CONFIDENCE = 0.75


def _normalize_domain(raw: str) -> str:
    candidate = raw.strip()
    if "://" in candidate:
        candidate = urlparse(candidate).hostname or candidate
    candidate = candidate.split("/")[0]
    return normalize_hostname(candidate)


async def discover_competitors(
    *,
    session: Session,
    router: ModelRouter,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    store_url: str,
    identity: StoreIdentity,
    max_suggestions: int = 10,
    timeout_seconds: float = 60.0,
) -> tuple[list[Competitor], list[uuid.UUID]]:
    """Returns (persisted competitors, evidence row ids). Empty results on
    any AI-call failure/timeout — same catch shape as resolve_store_identity
    — competitor suggestion failing must never block registration or the
    rest of the run."""
    location = ", ".join(part for part in (identity.city, identity.country) if part) or "غير معروف"
    messages = COMPETITOR_DISCOVERY_PROMPT.render(
        brand_name=identity.brand_name,
        business_type=identity.business_type or "غير محدد",
        location=location,
        categories=", ".join(identity.categories) or "غير محددة",
    )

    try:
        response = await asyncio.wait_for(
            router.execute(
                session=session,
                task_type="competitor_discovery_search",
                messages=messages,
                research_run_id=research_run_id,
                agent_run_id=agent_run_id,
                prompt_name=COMPETITOR_DISCOVERY_PROMPT.name,
                prompt_version=COMPETITOR_DISCOVERY_PROMPT.version,
                schema_version=COMPETITOR_DISCOVERY_PROMPT.schema_version,
                response_schema=CompetitorDiscoveryResult,
                enable_web_search=True,
            ),
            timeout=timeout_seconds,
        )
    except (AIProviderError, RuntimeError, TimeoutError, asyncio.TimeoutError):
        return [], []

    if response.parsed is None or response.execution_id is None:
        return [], []

    result = CompetitorDiscoveryResult.model_validate(response.parsed)
    client_hostname = normalize_hostname(urlparse(store_url).hostname or "")

    aggregate_evidence = Evidence(
        store_id=store_id,
        research_run_id=research_run_id,
        source_type=EvidenceSourceType.ai_execution,
        source_id=response.execution_id,
        confidence=None,
        summary=f"Competitor discovery via web search found {len(result.competitors)} candidate(s)",
    )
    session.add(aggregate_evidence)
    session.commit()
    session.refresh(aggregate_evidence)
    evidence_ids: list[uuid.UUID] = [aggregate_evidence.id]

    persisted: list[Competitor] = []
    for discovered in result.competitors[:max_suggestions]:
        normalized = _normalize_domain(discovered.domain)
        if not normalized or normalized == client_hostname or is_synthetic_test_domain(normalized):
            continue
        if classify_known_domain(normalized) is not None:
            # A known marketplace/social/publisher/etc. — never a direct
            # competitor, regardless of what the model called it.
            continue

        competitor_evidence_ids: list[str] = []
        for source in discovered.sources:
            citation = Evidence(
                store_id=store_id,
                research_run_id=research_run_id,
                source_type=EvidenceSourceType.web_search_citation,
                source_id=uuid.uuid5(uuid.NAMESPACE_URL, source.url),
                confidence=discovered.confidence,
                summary=f"{source.title} — {source.url}",
            )
            session.add(citation)
            session.commit()
            session.refresh(citation)
            evidence_ids.append(citation.id)
            competitor_evidence_ids.append(str(citation.id))

        competitor = get_or_create_competitor(
            session,
            store_id=store_id,
            domain=normalized,
            competitor_type=CompetitorType.identity_web_search,
            research_run_id=research_run_id,
            name=discovered.name,
        )

        auto_confirm = (
            len(discovered.sources) >= AUTO_CONFIRM_MIN_SOURCES or discovered.confidence >= AUTO_CONFIRM_MIN_CONFIDENCE
        )
        if competitor.confirmation_status == "pending_user_confirmation" and auto_confirm:
            competitor.confirmation_status = "auto_confirmed"
        # Never downgrade a classification a stronger signal (or a human)
        # already set — only fill in when this competitor has no verdict yet.
        if competitor.classification == "unknown":
            competitor.classification = "direct_competitor" if auto_confirm else "unknown"
            competitor.classification_confidence = discovered.confidence
            competitor.relevance_score = discovered.confidence
            competitor.discovery_reason = discovered.description or "منافس مقترح عبر البحث الهوياتي"
        competitor.evidence_ids = sorted(set(competitor.evidence_ids) | set(competitor_evidence_ids))
        session.add(competitor)
        session.commit()
        session.refresh(competitor)
        persisted.append(competitor)

    return persisted, evidence_ids
