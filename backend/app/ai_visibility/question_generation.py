"""Phase 5 (extended by the SIGNUP re-scope, then narrowed again by the
90-search re-scope) — generates natural buyer questions from a store's
resolved identity (+ known competitor names for grounding), persisted
per-store so week-over-week tracking has something stable to compare
against. Deliberately not fed into Intent/PromptFamily/PromptVariant — see
VisibilityQuestion's docstring.

One AI call per category (9 total, run concurrently) rather than one big
call for the whole target — confirmed live that a single big ask makes
gpt-4o-mini silently under-deliver (a compliance gap, not a truncation
one: well under its own token budget). A narrower per-category ask is a
far more reliable count target for this model.

TARGET_TOTAL_QUESTIONS = 60 (down from an earlier 135 — the 90-search
re-scope needs 60 for ChatGPT + 30 of those same 60 for Google, not 135).
Each category is asked for QUESTIONS_PER_CATEGORY (7) — slightly more than
60/9 — so the 9 calls together comfortably clear 60 even if a couple of
categories under-deliver or one fails outright; the aggregate is then
trimmed to exactly TARGET_TOTAL_QUESTIONS via a round-robin pass across
categories, so no single category can crowd out the others."""

import asyncio
import uuid
from collections import defaultdict, deque

from sqlmodel import Session, select

from app.models.evidence import Evidence, EvidenceSourceType
from app.models.stable_intent import normalize_topic
from app.models.visibility_run import VisibilityQuestion
from app.prompts.visibility_question_generation import VISIBILITY_QUESTION_GENERATION_PROMPT
from app.providers.ai.base import AIProviderError
from app.providers.ai.router import ModelRouter
from app.schemas.store_identity import StoreIdentity
from app.schemas.visibility_question import QUESTION_CATEGORIES, QuestionGenerationResult

TARGET_TOTAL_QUESTIONS = 60
QUESTIONS_PER_CATEGORY = 7
CATEGORY_CALL_TIMEOUT_SECONDS = 60.0
CATEGORY_CALL_MAX_CONCURRENCY = 8
# A near-duplicate paraphrase ("أين أجد باقة ورد جيدة؟" vs "من أين أشتري
# باقة ورد جيدة؟") won't collide under normalize_topic's exact-match dedup
# — both normalize to different strings despite asking the same thing.
# Jaccard token-overlap against everything already accepted this run is a
# deterministic, zero-extra-AI-call way to catch that, reusing the same
# token-set-overlap idiom app.competitors.classification already relies on
# for a structurally identical problem (specific-word overlap, not exact
# string match).
NEAR_DUPLICATE_JACCARD_THRESHOLD = 0.6


def _question_tokens(normalized_text: str) -> set[str]:
    return {t for t in normalized_text.split() if len(t) > 1}


def _is_near_duplicate(tokens: set[str], seen_token_sets: list[set[str]]) -> bool:
    if not tokens:
        return False
    for other in seen_token_sets:
        union = tokens | other
        if not union:
            continue
        jaccard = len(tokens & other) / len(union)
        if jaccard >= NEAR_DUPLICATE_JACCARD_THRESHOLD:
            return True
    return False


async def _generate_for_category(
    *,
    session: Session,
    router: ModelRouter,
    category: str,
    business_type: str,
    categories_text: str,
    location: str,
    competitor_names_text: str,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    semaphore: asyncio.Semaphore,
) -> tuple[str, list[str], uuid.UUID | None]:
    """Always returns (category, texts, execution_id) — never raises. One
    category's call failing/timing out just means fewer questions in that
    category, never an aborted overall generation."""
    messages = VISIBILITY_QUESTION_GENERATION_PROMPT.render(
        business_type=business_type, categories=categories_text, location=location,
        competitor_names=competitor_names_text, category_key=category, count=str(QUESTIONS_PER_CATEGORY),
    )
    async with semaphore:
        try:
            response = await asyncio.wait_for(
                router.execute(
                    session=session,
                    task_type="visibility_question_generation",
                    messages=messages,
                    research_run_id=research_run_id,
                    agent_run_id=agent_run_id,
                    prompt_name=VISIBILITY_QUESTION_GENERATION_PROMPT.name,
                    prompt_version=VISIBILITY_QUESTION_GENERATION_PROMPT.version,
                    schema_version=VISIBILITY_QUESTION_GENERATION_PROMPT.schema_version,
                    response_schema=QuestionGenerationResult,
                    max_tokens=2000,
                ),
                timeout=CATEGORY_CALL_TIMEOUT_SECONDS,
            )
        except (AIProviderError, RuntimeError, TimeoutError, asyncio.TimeoutError):
            return category, [], None

    if response.parsed is None or response.execution_id is None:
        return category, [], None

    result = QuestionGenerationResult.model_validate(response.parsed)
    return category, [q.text for q in result.questions], response.execution_id


async def generate_visibility_questions(
    *,
    session: Session,
    router: ModelRouter,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    identity: StoreIdentity,
    competitor_names: list[str],
) -> tuple[list[VisibilityQuestion], list[uuid.UUID]]:
    """Returns (newly-persisted questions, evidence ids — one per
    successful category call). Re-running on a store that already has
    questions only adds genuinely new ones (dedup by normalize_topic
    against existing active rows), never duplicates. A category whose call
    fails simply contributes zero questions — never blocks the others or
    the rest of the run."""
    location = ", ".join(part for part in (identity.city, identity.country) if part) or "غير معروف"
    business_type = identity.business_type or "غير محدد"
    categories_text = ", ".join(identity.categories) or "غير محددة"
    competitor_names_text = ", ".join(competitor_names[:8]) or "لا يوجد"

    semaphore = asyncio.Semaphore(CATEGORY_CALL_MAX_CONCURRENCY)
    results = await asyncio.gather(
        *(
            _generate_for_category(
                session=session, router=router, category=category, business_type=business_type,
                categories_text=categories_text, location=location, competitor_names_text=competitor_names_text,
                research_run_id=research_run_id, agent_run_id=agent_run_id, semaphore=semaphore,
            )
            for category in QUESTION_CATEGORIES
        )
    )

    existing = session.exec(
        select(VisibilityQuestion.normalized_text).where(
            VisibilityQuestion.store_id == store_id, VisibilityQuestion.is_active == True  # noqa: E712
        )
    ).all()
    seen_normalized = set(existing)
    seen_token_sets = [_question_tokens(n) for n in existing]

    # Pass 1 — exact + near-duplicate dedup against existing rows AND
    # everything already accepted this run, queued per category so the
    # round-robin trim below can be fair across categories.
    candidates_by_category: dict[str, deque[tuple[str, str]]] = defaultdict(deque)
    execution_id_by_category: dict[str, uuid.UUID] = {}
    for category, texts, execution_id in results:
        if execution_id is None:
            continue
        execution_id_by_category[category] = execution_id
        for text in texts:
            normalized = normalize_topic(text)
            if not normalized or normalized in seen_normalized:
                continue
            tokens = _question_tokens(normalized)
            if _is_near_duplicate(tokens, seen_token_sets):
                continue
            seen_normalized.add(normalized)
            seen_token_sets.append(tokens)
            candidates_by_category[category].append((text, normalized))

    # Pass 2 — round-robin across categories up to TARGET_TOTAL_QUESTIONS,
    # so one over-productive category can never crowd out the others.
    remaining_categories = [c for c in QUESTION_CATEGORIES if candidates_by_category.get(c)]
    selected: list[tuple[str, str, str]] = []
    while len(selected) < TARGET_TOTAL_QUESTIONS and remaining_categories:
        for category in list(remaining_categories):
            if len(selected) >= TARGET_TOTAL_QUESTIONS:
                break
            queue = candidates_by_category[category]
            text, normalized = queue.popleft()
            selected.append((category, text, normalized))
            if not queue:
                remaining_categories.remove(category)

    persisted: list[VisibilityQuestion] = []
    persisted_count_by_category: dict[str, int] = defaultdict(int)
    for category, text, normalized in selected:
        question = VisibilityQuestion(
            store_id=store_id, text=text, category=category,
            normalized_text=normalized, source_research_run_id=research_run_id,
        )
        session.add(question)
        persisted.append(question)
        persisted_count_by_category[category] += 1

    evidence_ids: list[uuid.UUID] = []
    for category, execution_id in execution_id_by_category.items():
        evidence = Evidence(
            store_id=store_id, research_run_id=research_run_id, source_type=EvidenceSourceType.ai_execution,
            source_id=execution_id, confidence=None,
            summary=f"Generated {persisted_count_by_category.get(category, 0)} new '{category}' visibility question(s)",
        )
        session.add(evidence)
        evidence_ids.append(evidence.id)

    if persisted or evidence_ids:
        session.commit()
        for question in persisted:
            session.refresh(question)

    return persisted, evidence_ids
