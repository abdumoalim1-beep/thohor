import asyncio
import uuid
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.core.storage import RawArtifactStore
from app.core.urls import normalize_hostname
from app.crawler.extract import extract_page_facts
from app.crawler.fetch import FetchError, safe_fetch
from app.crawler.security import CrawlSecurityPolicy
from app.models.catalog import Category, Product
from app.models.competitor import Competitor, CompetitorRelationship, RelationshipSource
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.intent import Intent
from app.models.page_intelligence import PageGapAnalysis
from app.models.serp import SerpObservation
from app.prompts.page_gap_analysis import PAGE_GAP_ANALYSIS_PROMPT
from app.providers.ai.router import ModelRouter
from app.schemas.page_gap_analysis import PageGapAnalysisResult

WEAK_RANK_THRESHOLD = 10


class GapCandidate:
    def __init__(self, intent: Intent, competitor: Competitor, competitor_url: str, competitor_rank: int):
        self.intent = intent
        self.competitor = competitor
        self.competitor_url = competitor_url
        self.competitor_rank = competitor_rank


def _select_gap_candidates(session: Session, research_run_id: uuid.UUID, max_gaps: int) -> list[GapCandidate]:
    """Weak intents (client_rank missing, or outside the top 10) paired with
    the strongest competitor already discovered for that same intent in
    Part D1 — no new discovery logic here, just picking from what's already
    in competitor_relationships."""
    observations = session.exec(
        select(SerpObservation).where(SerpObservation.research_run_id == research_run_id)
    ).all()
    weak_observation_by_intent: dict[uuid.UUID, SerpObservation] = {
        obs.intent_id: obs
        for obs in observations
        if obs.client_rank is None or obs.client_rank > WEAK_RANK_THRESHOLD
    }
    if not weak_observation_by_intent:
        return []

    candidates: list[GapCandidate] = []
    for intent_id, observation in weak_observation_by_intent.items():
        best_relationship = session.exec(
            select(CompetitorRelationship)
            .where(CompetitorRelationship.research_run_id == research_run_id)
            .where(CompetitorRelationship.intent_id == intent_id)
            .where(CompetitorRelationship.source == RelationshipSource.serp)
            .where(CompetitorRelationship.rank_or_position.is_not(None))
            .order_by(CompetitorRelationship.rank_or_position.asc())  # type: ignore[union-attr]
        ).first()
        if best_relationship is None:
            continue

        competitor = session.get(Competitor, best_relationship.competitor_id)
        if competitor is None:
            continue

        competitor_url = next(
            (r.get("url") for r in observation.results if normalize_hostname(r.get("domain", "")) == competitor.domain),
            None,
        )
        if not competitor_url:
            continue

        intent = session.get(Intent, intent_id)
        if intent is None:
            continue

        candidates.append(GapCandidate(intent, competitor, competitor_url, best_relationship.rank_or_position))

    candidates.sort(key=lambda c: c.competitor_rank)
    return candidates[:max_gaps]


def build_gap_candidate(
    session: Session, research_run_id: uuid.UUID, intent_id: uuid.UUID, competitor_id: uuid.UUID
) -> GapCandidate | None:
    """Builds a single GapCandidate for one specific (intent, competitor)
    pair — used by Group D2's competitor_deep_dive/page_compare research
    tasks, which target a specific pair the Planner proposed, unlike
    _select_gap_candidates which scans all weak intents for the batch
    path."""
    intent = session.get(Intent, intent_id)
    competitor = session.get(Competitor, competitor_id)
    if intent is None or competitor is None:
        return None

    observation = session.exec(
        select(SerpObservation)
        .where(SerpObservation.research_run_id == research_run_id)
        .where(SerpObservation.intent_id == intent_id)
    ).first()
    if observation is None:
        return None

    competitor_url = next(
        (r.get("url") for r in observation.results if normalize_hostname(r.get("domain", "")) == competitor.domain),
        None,
    )
    if not competitor_url:
        return None

    best_relationship = session.exec(
        select(CompetitorRelationship)
        .where(CompetitorRelationship.research_run_id == research_run_id)
        .where(CompetitorRelationship.intent_id == intent_id)
        .where(CompetitorRelationship.competitor_id == competitor_id)
        .where(CompetitorRelationship.source == RelationshipSource.serp)
        .order_by(CompetitorRelationship.rank_or_position.asc())  # type: ignore[union-attr]
    ).first()
    rank = best_relationship.rank_or_position if best_relationship and best_relationship.rank_or_position else 1

    return GapCandidate(intent, competitor, competitor_url, rank)


def _summarize_our_catalog(session: Session, store_id: uuid.UUID, limit: int = 60) -> str:
    categories = session.exec(select(Category).where(Category.store_id == store_id)).all()
    products = session.exec(select(Product).where(Product.store_id == store_id)).all()
    lines = [f"- تصنيف: {c.name}" for c in categories[:limit] if c.name]
    lines += [f"- منتج: {p.name}" for p in products[:limit] if p.name]
    return "\n".join(lines) or "(لا توجد بيانات كتالوج)"


def _summarize_competitor_page(facts) -> str:
    lines = [f"- العنوان: {facts.title}" if facts.title else None, f"- H1: {facts.h1}" if facts.h1 else None]
    if facts.meta_description:
        lines.append(f"- الوصف: {facts.meta_description}")
    for entry in facts.json_ld[:5]:
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            lines.append(f"- عنصر JSON-LD: {name.strip()}")
    return "\n".join(line for line in lines if line) or "(لا توجد بيانات مستخرجة)"


async def analyze_one_gap_candidate(
    *,
    session: Session,
    router: ModelRouter,
    storage: RawArtifactStore,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    candidate: GapCandidate,
    our_catalog_summary: str,
    crawl_policy: CrawlSecurityPolicy,
) -> PageGapAnalysis | None:
    """One competitor-page-vs-catalog gap analysis: crawl (same secured
    crawler as Group A — no exception for external competitor domains),
    extract, ask the router what it covers that our catalog doesn't, then
    persist + evidence. Factored out of the Group D batch loop so Group
    D2's competitor_deep_dive/page_compare research_tasks can reuse it for
    a single Planner-targeted candidate — the batch loop below is
    unchanged, it just calls this once per candidate now."""
    try:
        fetch_result = await safe_fetch(candidate.competitor_url, crawl_policy)
    except (FetchError, ValueError):
        # ValueError covers UnsafeURLError from crawler/security.py — a
        # competitor page that fails our own SSRF/scheme checks is simply
        # skipped, same as any other unfetchable page.
        return None

    raw_uri = storage.put_text(f"stores/{store_id}/runs/{research_run_id}/competitor-pages", fetch_result.text)
    facts = extract_page_facts(fetch_result.url, fetch_result.text, urlparse(fetch_result.url).hostname)
    competitor_page_summary = _summarize_competitor_page(facts)

    messages = PAGE_GAP_ANALYSIS_PROMPT.render(
        intent_topic=candidate.intent.topic,
        our_catalog_summary=our_catalog_summary,
        competitor_url=fetch_result.url,
        competitor_page_summary=competitor_page_summary,
    )

    response = await router.execute(
        session=session,
        task_type="page_gap_analysis",
        messages=messages,
        research_run_id=research_run_id,
        agent_run_id=agent_run_id,
        prompt_name=PAGE_GAP_ANALYSIS_PROMPT.name,
        prompt_version=PAGE_GAP_ANALYSIS_PROMPT.version,
        schema_version=PAGE_GAP_ANALYSIS_PROMPT.schema_version,
        response_schema=PageGapAnalysisResult,
    )

    if response.parsed is None:
        return None

    result = PageGapAnalysisResult.model_validate(response.parsed)

    analysis = PageGapAnalysis(
        store_id=store_id,
        intent_id=candidate.intent.id,
        competitor_id=candidate.competitor.id,
        research_run_id=research_run_id,
        agent_run_id=agent_run_id,
        competitor_url=fetch_result.url,
        gaps=result.gaps,
        recommendation_summary=result.recommendation_summary,
        confidence=result.confidence,
        raw_artifact_uri=raw_uri,
    )
    session.add(analysis)
    session.commit()
    session.refresh(analysis)

    session.add(
        Evidence(
            store_id=store_id,
            research_run_id=research_run_id,
            source_type=EvidenceSourceType.page_gap_analysis,
            source_id=analysis.id,
            confidence=result.confidence,
            summary=f"Gap vs {candidate.competitor.domain} for '{candidate.intent.topic}': {result.recommendation_summary}",
        )
    )
    session.commit()

    return analysis


async def _analyze_one_gap_candidate_bounded(
    semaphore: asyncio.Semaphore, **kwargs
) -> PageGapAnalysis | None:
    """Part H5 — bounds how many competitor pages are being crawled +
    AI-compared at once (PAGE_ANALYSIS_MAX_CONCURRENCY). Safe to share one
    `session` across these concurrently-gathered calls (Part H7):
    analyze_one_gap_candidate's only session writes
    (session.add/session.commit for PageGapAnalysis and Evidence) happen
    strictly after its last await with nothing else interleaved, so no two
    coroutines' writes can ever actually execute at the same instant even
    though their network waits (fetch, AI call) genuinely overlap."""
    async with semaphore:
        return await analyze_one_gap_candidate(**kwargs)


async def run_page_intelligence_agent(
    *,
    session: Session,
    router: ModelRouter,
    storage: RawArtifactStore,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    max_gaps: int,
    crawl_policy: CrawlSecurityPolicy,
    max_concurrency: int = 1,
) -> list[PageGapAnalysis]:
    """For the weakest intents where a competitor is strong, crawls the
    competitor's winning page and asks the router to identify what it
    covers that our own catalog summary does not.

    Part H5 (post-G-B directive): independent candidates are crawled and
    analyzed concurrently (bounded by max_concurrency, i.e.
    Settings.page_analysis_max_concurrency) instead of one at a time."""
    candidates = _select_gap_candidates(session, research_run_id, max_gaps)
    our_catalog_summary = _summarize_our_catalog(session, store_id)
    if not candidates:
        return []

    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    results = await asyncio.gather(
        *(
            _analyze_one_gap_candidate_bounded(
                semaphore,
                session=session,
                router=router,
                storage=storage,
                store_id=store_id,
                research_run_id=research_run_id,
                agent_run_id=agent_run_id,
                candidate=candidate,
                our_catalog_summary=our_catalog_summary,
                crawl_policy=crawl_policy,
            )
            for candidate in candidates
        )
    )

    return [analysis for analysis in results if analysis is not None]
