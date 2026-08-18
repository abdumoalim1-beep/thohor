import uuid

from sqlmodel import Session, select

from app.core.language import language_display_name
from app.models.ai_visibility import PromptFamily, PromptVariant
from app.models.intent import Intent
from app.prompts.prompt_family_generation import PROMPT_FAMILY_GENERATION_PROMPT
from app.providers.ai.router import ModelRouter
from app.schemas.prompt_family_generation import PromptFamilyResult


def select_top_intents(session: Session, research_run_id: uuid.UUID, max_intents: int) -> list[Intent]:
    """AI Visibility testing is expensive (real providers, real cost) — only
    the highest-confidence intents from this run are tested, never all of
    them (PRD section 40: '5-10 prompt variants لأهم intents'). Part G-B1:
    quality-rejected intents (is_accepted=False) never reach here — no
    natural-question prompts get built from a scraped page title."""
    intents = session.exec(
        select(Intent)
        .where(Intent.research_run_id == research_run_id)
        .where(Intent.is_accepted == True)  # noqa: E712
        .order_by(Intent.confidence.desc())  # type: ignore[arg-type]
    ).all()
    return list(intents[:max_intents])


async def run_prompt_family_agent(
    *,
    session: Session,
    router: ModelRouter,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    intents: list[Intent],
    max_prompts_per_intent: int,
) -> list[PromptVariant]:
    """Generates natural-language questions per intent — grounded in the
    intent's topic/category, in the store's target market language (same
    lesson as intent_expansion: an unspecified language defaults to
    whatever the model feels like, not necessarily Arabic)."""
    all_variants: list[PromptVariant] = []

    for intent in intents:
        messages = PROMPT_FAMILY_GENERATION_PROMPT.render(
            target_language=language_display_name(intent.language),
            topic=intent.topic,
            category=intent.category or "",
            max_prompts=str(max_prompts_per_intent),
        )
        try:
            response = await router.execute(
                session=session,
                task_type="prompt_family_generation",
                messages=messages,
                research_run_id=research_run_id,
                agent_run_id=agent_run_id,
                prompt_name=PROMPT_FAMILY_GENERATION_PROMPT.name,
                prompt_version=PROMPT_FAMILY_GENERATION_PROMPT.version,
                schema_version=PROMPT_FAMILY_GENERATION_PROMPT.schema_version,
                response_schema=PromptFamilyResult,
            )
        except Exception:  # noqa: BLE001 — one intent failing to generate prompts shouldn't block the others
            continue

        if response.parsed is None:
            continue

        result = PromptFamilyResult.model_validate(response.parsed)

        family = PromptFamily(intent_id=intent.id, research_run_id=research_run_id, agent_run_id=agent_run_id)
        session.add(family)
        session.commit()
        session.refresh(family)

        for text in result.prompts[:max_prompts_per_intent]:
            if not text.strip():
                continue
            variant = PromptVariant(prompt_family_id=family.id, text=text.strip())
            session.add(variant)
            session.commit()
            session.refresh(variant)
            all_variants.append(variant)

    return all_variants
