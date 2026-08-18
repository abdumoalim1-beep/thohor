"""Part 2 MVP — glues multi_engine_runner + answer_analysis_engine into one
call: run every active question through every configured engine, then
analyze every successful answer. Kept out of the Celery task itself (same
division of responsibility as ResearchOrchestrator vs execute_research_run_task)
so this stays testable without a worker."""

import uuid
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.ai_visibility.answer_analysis_engine import analyze_visibility_run
from app.ai_visibility.multi_engine_runner import build_deterministic_search_analysis, run_visibility_run
from app.competitors.classification import is_business_competitor
from app.core.domain import registered_domain
from app.core.urls import normalize_hostname
from app.crawler.store_intelligence import _guess_brand_name_from_domain
from app.models.catalog import Brand
from app.models.competitor import Competitor
from app.models.research import AgentRun, ResearchRun
from app.models.store import Store
from app.models.visibility_run import EngineAnswer, EngineAnswerAnalysis, VisibilityQuestion, VisibilityRun
from app.providers.ai.router import ModelRouter
from app.providers.search.base import SearchProvider


def _resolve_brand_name(session: Session, store: Store) -> str:
    """Same priority as get_store_understanding's display_name resolution:
    a real crawl-derived Brand row first, then the most recent resolved
    identity_agent_run's brand_name (the only real name available for a
    catalog_blocked store — Phase 1's whole point), then an honest
    domain-derived guess as the last resort."""
    brand = session.exec(select(Brand).where(Brand.store_id == store.id)).first()
    if brand is not None and brand.name and brand.name != _guess_brand_name_from_domain(store.url):
        return brand.name

    identity_runs = session.exec(
        select(AgentRun)
        .join(ResearchRun, AgentRun.research_run_id == ResearchRun.id)  # type: ignore[arg-type]
        .where(ResearchRun.store_id == store.id, AgentRun.agent_type == "store_identity_agent_run")
        .order_by(AgentRun.created_at.desc())  # type: ignore[union-attr]
    ).all()
    for agent_run in identity_runs:
        findings = agent_run.findings or {}
        if findings.get("skipped"):
            continue
        brand_name = findings.get("brand_name")
        if brand_name:
            return str(brand_name)

    return brand.name if brand is not None and brand.name else _guess_brand_name_from_domain(store.url)


def _resolve_brand_aliases(session: Session, store: Store) -> list[str]:
    """Aliases recorded on the store's Brand row — includes the store's
    own domain and any prior name once a user has confirmed/edited a name
    via POST /stores/{id}/brand-name (see confirm_store_brand_name in
    app.api.stores), so an AI answer still using an older name or a
    domain-derived guess is still recognized as mentioning this brand.
    Never changes which single name _resolve_brand_name treats as
    primary — purely additive grounding for the analysis prompt."""
    brand = session.exec(select(Brand).where(Brand.store_id == store.id)).first()
    return list(brand.aliases) if brand is not None and brand.aliases else []


def _real_business_competitors(session: Session, store_id: uuid.UUID) -> list[Competitor]:
    """The one predicate this whole codebase uses to decide 'this is a
    real competitor, not a marketplace/social/video/forum/generic
    platform' (app.competitors.classification.is_business_competitor) —
    confirmed live that skipping this let Instagram and YouTube show up as
    'top competitors' in the /signup report, since a plain 'not rejected
    by the user' filter still includes every classification value,
    including social/video/marketplace/unknown."""
    competitors = session.exec(
        select(Competitor).where(Competitor.store_id == store_id, Competitor.confirmation_status != "user_rejected")
    ).all()
    return [c for c in competitors if is_business_competitor(c)]


def _resolve_competitor_names(session: Session, store_id: uuid.UUID) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for competitor in _real_business_competitors(session, store_id):
        if competitor.name not in seen:
            seen.add(competitor.name)
            names.append(competitor.name)
    return names


def _resolve_competitor_domain_names(session: Session, store_id: uuid.UUID) -> dict[str, str]:
    """registered_domain -> display name, for the deterministic Google
    analysis (matching a SERP result's hostname against known competitors
    without a second AI call)."""
    return {registered_domain(c.domain): c.name for c in _real_business_competitors(session, store_id)}


async def run_visibility_measurement(
    *, session: Session, router: ModelRouter, run: VisibilityRun, search_provider: SearchProvider | None = None
) -> tuple[VisibilityRun, list[EngineAnswerAnalysis]]:
    """Operates on an already-created VisibilityRun row (see
    create_pending_visibility_run) — never creates one itself, so the id a
    caller already has (e.g. handed back from the trigger endpoint) stays
    the canonical one throughout."""
    store = session.get(Store, run.store_id)
    if store is None:
        raise ValueError(f"store {run.store_id} not found")

    run = await run_visibility_run(
        session=session, router=router, run=run, search_provider=search_provider,
        country=store.country or "sa", language=store.language or "ar",
    )

    answers = session.exec(select(EngineAnswer).where(EngineAnswer.visibility_run_id == run.id)).all()
    questions = session.exec(select(VisibilityQuestion).where(VisibilityQuestion.store_id == run.store_id)).all()
    questions_by_id = {q.id: q.text for q in questions}

    # Google's rows are analyzed deterministically (rank IS the mention
    # rank — no natural-language text to classify) — only the AI-text
    # engines (chatgpt today) go through the AI classifier.
    ai_answers = [a for a in answers if a.engine != "google"]
    google_answers = [a for a in answers if a.engine == "google" and a.status == "success"]

    analyses = await analyze_visibility_run(
        session=session, router=router, answers=ai_answers, questions_by_id=questions_by_id,
        brand_name=_resolve_brand_name(session, store), competitor_names=_resolve_competitor_names(session, run.store_id),
        brand_aliases=_resolve_brand_aliases(session, store),
    )

    if google_answers:
        client_hostname = normalize_hostname(urlparse(store.url).hostname or "")
        competitor_domain_names = _resolve_competitor_domain_names(session, run.store_id)
        for answer in google_answers:
            analysis = build_deterministic_search_analysis(
                answer, client_hostname=client_hostname, competitor_domain_names=competitor_domain_names
            )
            session.add(analysis)
            analyses.append(analysis)
        session.commit()
        for analysis in analyses[-len(google_answers):]:
            session.refresh(analysis)

    return run, analyses
