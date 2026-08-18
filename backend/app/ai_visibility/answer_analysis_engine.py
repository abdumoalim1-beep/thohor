"""Part 2 MVP — classifies one already-captured EngineAnswer's raw text:
was the brand mentioned, was it actually recommended (vs a bare mention),
where did it rank, who else was mentioned. Grounded with the real brand
name and known competitor names (already gathered elsewhere in this
codebase) so the model classifies against real entities, never invented
ones — same discipline as identity/competitor discovery."""

import asyncio
import uuid

from sqlmodel import Session

from app.models.visibility_run import EngineAnswer, EngineAnswerAnalysis
from app.prompts.answer_analysis import ANSWER_ANALYSIS_PROMPT
from app.providers.ai.base import AIProviderError
from app.providers.ai.router import ModelRouter
from app.schemas.answer_analysis import MENTION_TYPES, AnswerAnalysisResult


def _brand_name_with_aliases(brand_name: str, brand_aliases: list[str]) -> str:
    """Folds aliases into the same {brand_name} prompt slot rather than
    adding a new template variable — a user-edited/confirmed name (see
    POST /stores/{id}/brand-name) pushes the previously-resolved name and
    the store's own domain into Brand.aliases so an AI answer that still
    uses the old name/domain-derived guess is still recognized as
    mentioning this brand."""
    unique_aliases = [a for a in dict.fromkeys(brand_aliases) if a and a != brand_name]
    if not unique_aliases:
        return brand_name
    return f"{brand_name} (يُعرف أيضًا بالأسماء: {', '.join(unique_aliases[:6])})"


async def analyze_engine_answer(
    *,
    session: Session,
    router: ModelRouter,
    engine_answer: EngineAnswer,
    question_text: str,
    brand_name: str,
    competitor_names: list[str],
    brand_aliases: list[str] | None = None,
    timeout_seconds: float = 60.0,
) -> EngineAnswerAnalysis | None:
    """Returns None (never raises) when the answer wasn't a success in the
    first place, the AI call fails/times out, or the model returns an
    unrecognized mention_type — analysis failing must never block the run,
    same as every other AI-call site in this codebase."""
    if engine_answer.status != "success" or not engine_answer.raw_answer:
        return None

    messages = ANSWER_ANALYSIS_PROMPT.render(
        brand_name=_brand_name_with_aliases(brand_name, brand_aliases or []),
        competitor_names=", ".join(competitor_names[:10]) or "لا يوجد",
        question_text=question_text,
        answer_text=engine_answer.raw_answer,
    )

    try:
        response = await asyncio.wait_for(
            router.execute(
                session=session,
                task_type="answer_analysis",
                messages=messages,
                prompt_name=ANSWER_ANALYSIS_PROMPT.name,
                prompt_version=ANSWER_ANALYSIS_PROMPT.version,
                schema_version=ANSWER_ANALYSIS_PROMPT.schema_version,
                response_schema=AnswerAnalysisResult,
            ),
            timeout=timeout_seconds,
        )
    except (AIProviderError, RuntimeError, TimeoutError, asyncio.TimeoutError):
        return None

    if response.parsed is None:
        return None

    result = AnswerAnalysisResult.model_validate(response.parsed)
    if result.mention_type not in MENTION_TYPES:
        return None

    analysis = EngineAnswerAnalysis(
        engine_answer_id=engine_answer.id,
        store_id=engine_answer.store_id,
        brand_mentioned=result.brand_mentioned,
        mention_type=result.mention_type,
        mention_rank=result.mention_rank,
        recommendation_rank=result.recommendation_rank,
        competitors_mentioned=[c.model_dump() for c in result.competitors_mentioned],
        evidence_quote=result.evidence_quote,
        confidence=result.confidence,
    )
    session.add(analysis)
    session.commit()
    session.refresh(analysis)
    return analysis


async def analyze_visibility_run(
    *,
    session: Session,
    router: ModelRouter,
    answers: list[EngineAnswer],
    questions_by_id: dict[uuid.UUID, str],
    brand_name: str,
    competitor_names: list[str],
    brand_aliases: list[str] | None = None,
    max_concurrency: int = 8,
) -> list[EngineAnswerAnalysis]:
    """Analyzes every successful answer in a run. One answer's analysis
    failing (returns None) never stops the others — gather() over
    independent per-answer calls, same shape as multi_engine_runner's own
    per-question gather. Bounded at max_concurrency (default 8, matching
    multi_engine_runner.DEFAULT_MAX_CONCURRENCY) so this phase never fires
    more concurrent AI calls than the answer/search phase does — each call
    already commits its own row immediately (analyze_engine_answer), so
    this bound is purely about concurrency, not batching."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _bounded(answer: EngineAnswer) -> EngineAnswerAnalysis | None:
        async with semaphore:
            return await analyze_engine_answer(
                session=session, router=router, engine_answer=answer,
                question_text=questions_by_id.get(answer.question_id, ""),
                brand_name=brand_name, competitor_names=competitor_names, brand_aliases=brand_aliases,
            )

    results = await asyncio.gather(*(_bounded(answer) for answer in answers))
    return [r for r in results if r is not None]
