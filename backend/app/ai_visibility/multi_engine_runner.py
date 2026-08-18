"""Part 2 MVP (re-scoped, engine-first) — runs every active
VisibilityQuestion for a store through whichever answer engines are
actually configured. Modeled directly on
app.ai_visibility.visibility_engine's `_execute_one_probe`/
`run_ai_visibility_agent` (same "one call, one provider/model, no
route-fallback, a failure is an ordinary absent result not an exception"
shape) — that is how "one engine failing never fails the whole run" is
satisfied here too: reused proven code, not new resilience logic.

Deliberately a parallel system to run_ai_visibility_agent, not a change to
it: that engine measures the SEO-shaped Intent/PromptVariant pipeline
per-research-run; this measures persistent, natural VisibilityQuestion rows
on their own weekly cadence — two different lifecycles, see
VisibilityQuestion's own docstring.
"""

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.core.domain import registered_domain
from app.core.urls import normalize_hostname
from app.models.base import utcnow
from app.models.visibility_run import EngineAnswer, EngineAnswerAnalysis, VisibilityQuestion, VisibilityRun
from app.providers.ai.base import AIMessage, AIProviderError, AIRole
from app.providers.ai.router import ModelRouter
from app.providers.search.base import SearchProvider, SearchProviderError, SearchRequest
from app.prompts.visibility_question_answering import VISIBILITY_QUESTION_ANSWERING_PROMPT

AI_ANSWER_TIMEOUT_SECONDS = 60.0
GOOGLE_SEARCH_TIMEOUT_SECONDS = 30.0
# 90-search re-scope: 60 ChatGPT + 30 Google (not the earlier 135+45). The
# AI engine(s) run over at most AI_ENGINE_MAX_QUESTIONS questions per run
# (never the full historical backlog once a store has accumulated more
# than that across weekly reruns), and Google's GOOGLE_SEARCH_MAX_QUESTIONS
# is always a *subset of that same set* — never a separate slice of the
# full backlog — see _select_google_questions.
AI_ENGINE_MAX_QUESTIONS = 60
GOOGLE_SEARCH_MAX_QUESTIONS = 30
# Priority order for which categories fill Google's 30-question subset
# first — purchase-intent-shaped categories (per user direction), falling
# back to whatever's left only once those are exhausted.
GOOGLE_PRIORITY_CATEGORIES = (
    "recommendation", "local", "product_discovery", "comparison",
    "alternatives", "price", "occasion", "best", "problem_solution",
)
# Global concurrency budget shared by both the answer/search phase and the
# analysis phase (answer_analysis_engine.py) — one constant so "never
# exceed 8 concurrent operations" can't drift apart across the two.
DEFAULT_MAX_CONCURRENCY = 8


def _select_google_questions(questions: list[VisibilityQuestion], limit: int) -> list[VisibilityQuestion]:
    """Google's subset always comes from the same pool ChatGPT runs over —
    never a separate slice of the full backlog — prioritized toward
    purchase-intent-shaped categories, falling back to the rest only if
    those don't fill the budget."""
    by_category: dict[str, list[VisibilityQuestion]] = defaultdict(list)
    for question in questions:
        by_category[question.category].append(question)

    ordered_categories = [c for c in GOOGLE_PRIORITY_CATEGORIES if c in by_category]
    ordered_categories += [c for c in by_category if c not in GOOGLE_PRIORITY_CATEGORIES]

    selected: list[VisibilityQuestion] = []
    for category in ordered_categories:
        if len(selected) >= limit:
            break
        selected.extend(by_category[category][: limit - len(selected)])
    return selected


@dataclass(frozen=True)
class AnswerEngine:
    """One consumer-facing answer engine this system can measure against.
    search_enabled=True means this system asks the provider to actually
    browse the web for this call — a deliberate difference from
    app.ai_visibility.surfaces.AI_VISIBILITY_SURFACES (whose engines never
    ground today): visibility measurement wants the engine's best real
    answer, and grounding is exactly what makes citations (sources[])
    possible at all."""

    engine: str
    provider: str
    model: str
    search_enabled: bool = True


# Registry, not a hardcoded switch (same rationale as AI_VISIBILITY_SURFACES
# / OPPORTUNITY_DETECTORS elsewhere) — adding perplexity/gemini/claude later
# (per the reordered MVP plan) is one new entry here, no loop changes.
ANSWER_ENGINES: list[AnswerEngine] = [
    AnswerEngine(engine="chatgpt", provider="openai", model="gpt-4o-mini"),
]


def resolve_configured_answer_engines(router: ModelRouter) -> list[AnswerEngine]:
    """Only engines whose provider actually has a key configured — mirrors
    resolve_configured_surfaces' 'no key, simply absent, never a run
    failure' behavior."""
    configured = set(router.configured_provider_names)
    return [e for e in ANSWER_ENGINES if e.provider in configured]


async def _answer_one_question(
    router: ModelRouter,
    semaphore: asyncio.Semaphore,
    session: Session,
    engine: AnswerEngine,
    question: VisibilityQuestion,
    visibility_run_id: uuid.UUID,
) -> EngineAnswer:
    """Always returns a row — success or failure — never raises. This is
    the actual mechanism satisfying 'every attempted cell gets an explicit
    row, one question/engine failing doesn't abort the run'.

    Commits its own row immediately on completion rather than returning it
    for the caller to batch-commit after the whole gather resolves — the
    'save progressively, update completed_count after each result' rule.
    Safe to call this concurrently against one shared Session: asyncio is
    single-threaded/cooperative and Session.commit() itself contains no
    `await`, so two of these calls can never actually execute their DB
    calls at the same instant — the event loop always fully serializes
    them, same precondition answer_analysis_engine.py already relies on
    for its own per-analysis commit."""
    messages: list[AIMessage] = [
        AIMessage(role=AIRole.system, content=VISIBILITY_QUESTION_ANSWERING_PROMPT.system),
        AIMessage(role=AIRole.user, content=question.text),
    ]
    async with semaphore:
        try:
            response = await asyncio.wait_for(
                router.execute_single(
                    session=session,
                    provider_name=engine.provider,
                    model=engine.model,
                    task_type="visibility_question_answering",
                    messages=messages,
                    prompt_name=VISIBILITY_QUESTION_ANSWERING_PROMPT.name,
                    prompt_version=VISIBILITY_QUESTION_ANSWERING_PROMPT.version,
                    enable_web_search=engine.search_enabled,
                ),
                timeout=AI_ANSWER_TIMEOUT_SECONDS,
            )
        except (AIProviderError, RuntimeError, TimeoutError, asyncio.TimeoutError):
            answer = EngineAnswer(
                visibility_run_id=visibility_run_id, question_id=question.id, store_id=question.store_id,
                engine=engine.engine, engine_model=engine.model, status="failed",
            )
            session.add(answer)
            session.commit()
            session.refresh(answer)
            return answer

    answer = EngineAnswer(
        visibility_run_id=visibility_run_id, question_id=question.id, store_id=question.store_id,
        engine=engine.engine, engine_model=engine.model, status="success",
        raw_answer=response.text, sources=response.sources or [],
        ai_execution_id=response.execution_id,
    )
    session.add(answer)
    session.commit()
    session.refresh(answer)
    return answer


async def _search_one_question_google(
    search_provider: SearchProvider,
    semaphore: asyncio.Semaphore,
    session: Session,
    question: VisibilityQuestion,
    visibility_run_id: uuid.UUID,
    country: str,
    language: str,
) -> EngineAnswer:
    """Same 'always returns a row, never raises, commits its own row
    immediately' contract as _answer_one_question — real Google results via
    the same SearchProvider abstraction the existing SERP engine
    (run_serp_agent) already uses, run directly against the natural
    question text rather than an Intent/Keyword, mirroring how ChatGPT
    above bypasses PromptVariant entirely."""
    async with semaphore:
        try:
            response = await asyncio.wait_for(
                search_provider.search(SearchRequest(keyword=question.text, country=country, language=language, num_results=10)),
                timeout=GOOGLE_SEARCH_TIMEOUT_SECONDS,
            )
        except (SearchProviderError, RuntimeError, TimeoutError, asyncio.TimeoutError):
            answer = EngineAnswer(
                visibility_run_id=visibility_run_id, question_id=question.id, store_id=question.store_id,
                engine="google", engine_model=search_provider.underlying_provider_name, status="failed",
            )
            session.add(answer)
            session.commit()
            session.refresh(answer)
            return answer

    sources = [{"url": r.url, "title": r.title or r.domain} for r in response.results]
    answer = EngineAnswer(
        visibility_run_id=visibility_run_id, question_id=question.id, store_id=question.store_id,
        engine="google", engine_model=search_provider.underlying_provider_name, status="success", sources=sources,
    )
    session.add(answer)
    session.commit()
    session.refresh(answer)
    return answer


def build_deterministic_search_analysis(
    engine_answer: EngineAnswer, *, client_hostname: str, competitor_domain_names: dict[str, str]
) -> EngineAnswerAnalysis:
    """No AI call — a Google result's rank IS the mention rank, so this is
    read directly off the fetched sources rather than sent through
    answer_analysis_engine (which exists for classifying natural-language
    text, which a SERP result list isn't). Same deterministic-extraction
    principle used everywhere else in this codebase; the AI classifier is
    reserved for the genuinely ambiguous case (ChatGPT's prose)."""
    mention_rank: int | None = None
    competitors_mentioned: list[dict] = []
    for position, source in enumerate(engine_answer.sources, start=1):
        hostname = normalize_hostname(urlparse(source.get("url", "")).hostname or "")
        if not hostname:
            continue
        registered = registered_domain(hostname)
        if registered == registered_domain(client_hostname):
            if mention_rank is None:
                mention_rank = position
        elif registered in competitor_domain_names:
            competitors_mentioned.append({"name": competitor_domain_names[registered], "rank": position})

    return EngineAnswerAnalysis(
        engine_answer_id=engine_answer.id, store_id=engine_answer.store_id,
        brand_mentioned=mention_rank is not None,
        mention_type="mere_mention" if mention_rank is not None else "not_mentioned",
        mention_rank=mention_rank, recommendation_rank=None,
        competitors_mentioned=competitors_mentioned, evidence_quote=None, confidence=1.0,
    )


def create_pending_visibility_run(session: Session, store_id: uuid.UUID) -> VisibilityRun:
    """Mirrors ResearchOrchestrator.create_pending_run's contract: the
    caller (API endpoint, or a scheduled dispatch) creates and commits this
    row synchronously so it has a real id to hand back immediately;
    run_visibility_run then operates on that same row rather than creating
    its own — never two disconnected VisibilityRun rows for one trigger."""
    run = VisibilityRun(store_id=store_id, status="running", questions_count=0)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


async def run_visibility_run(
    *,
    session: Session,
    router: ModelRouter,
    run: VisibilityRun,
    search_provider: SearchProvider | None = None,
    country: str = "sa",
    language: str = "ar",
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
) -> VisibilityRun:
    """Runs up to AI_ENGINE_MAX_QUESTIONS active VisibilityQuestion rows for
    run.store_id through every configured AI answer engine, plus a real
    Google pass over a prioritized subset of that *same* question set when
    search_provider is given — updating the given (already-persisted) run
    in place. Zero configured engines/questions is a legitimate, honestly-
    recorded empty run — not an exception.

    ChatGPT and Google tasks are gathered together under one shared
    semaphore (never more than max_concurrency operations in flight at
    once, across both) so they genuinely run in parallel when safe, rather
    than as two sequential all-or-nothing phases — and each task commits
    its own EngineAnswer row the moment it finishes (see
    _answer_one_question/_search_one_question_google), so a live poll of
    this run's answer count advances continuously instead of jumping at
    the end of a batch."""
    all_questions = session.exec(
        select(VisibilityQuestion).where(VisibilityQuestion.store_id == run.store_id, VisibilityQuestion.is_active == True)  # noqa: E712
    ).all()
    run_questions = all_questions[:AI_ENGINE_MAX_QUESTIONS]
    engines = resolve_configured_answer_engines(router)
    google_questions = _select_google_questions(run_questions, GOOGLE_SEARCH_MAX_QUESTIONS) if search_provider is not None else []

    run.engines_attempted = [e.engine for e in engines] + (["google"] if google_questions else [])
    run.questions_count = len(run_questions)
    run.total_operations_planned = len(run_questions) * len(engines) + len(google_questions)
    session.add(run)
    session.commit()
    session.refresh(run)

    semaphore = asyncio.Semaphore(max_concurrency)
    tasks = [
        _answer_one_question(router, semaphore, session, engine, question, run.id)
        for question in run_questions
        for engine in engines
    ]
    tasks += [
        _search_one_question_google(search_provider, semaphore, session, question, run.id, country, language)
        for question in google_questions
    ]
    if tasks:
        await asyncio.gather(*tasks)

    run.status = "completed"
    run.completed_at = utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run
