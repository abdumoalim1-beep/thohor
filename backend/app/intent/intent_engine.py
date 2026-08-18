import uuid

from sqlmodel import Session, select

from app.core.language import language_display_name
from app.models.catalog import Category, Product
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.intent import Intent, IntentKeyword, IntentSource, Keyword
from app.models.stable_intent import StableIntent, normalize_topic
from app.prompts.intent_expansion import INTENT_EXPANSION_PROMPT
from app.providers.ai.router import ModelRouter
from app.schemas.intent_expansion import IntentExpansionResult


def get_or_create_stable_intent(
    session: Session,
    *,
    store_id: uuid.UUID,
    topic: str,
    country: str,
    language: str,
    intent_type: str | None = None,
) -> StableIntent:
    """The one place topic-text matching happens (Part F.5-0) — every other
    module references stable_intent_id, never re-derives identity from
    topic strings itself. Matched within (store, normalized_topic, country,
    language): the same real-world question asked again in a later
    research_run resolves to this same row instead of minting a new one."""
    normalized = normalize_topic(topic)
    existing = session.exec(
        select(StableIntent)
        .where(StableIntent.store_id == store_id)
        .where(StableIntent.normalized_topic == normalized)
        .where(StableIntent.country == country)
        .where(StableIntent.language == language)
    ).first()
    if existing is not None:
        return existing

    stable_intent = StableIntent(
        store_id=store_id,
        canonical_topic=topic.strip(),
        normalized_topic=normalized,
        country=country,
        language=language,
        locale=f"{country}_{language}",
        intent_type=intent_type,
    )
    session.add(stable_intent)
    session.commit()
    session.refresh(stable_intent)
    return stable_intent


def _get_or_create_keyword(session: Session, text: str, country: str, language: str) -> Keyword:
    normalized = text.strip()
    existing = session.exec(
        select(Keyword)
        .where(Keyword.text == normalized)
        .where(Keyword.country == country)
        .where(Keyword.language == language)
    ).first()
    if existing:
        return existing
    keyword = Keyword(text=normalized, country=country, language=language)
    session.add(keyword)
    session.commit()
    session.refresh(keyword)
    return keyword


def _attach_keywords(session: Session, intent: Intent, keywords: list[str], country: str, language: str) -> None:
    """First keyword in the list becomes is_primary — the one measured in
    SERP (Part B3). Order matters: callers should put the most
    representative phrase first."""
    for idx, text in enumerate(keywords):
        if not text.strip():
            continue
        keyword = _get_or_create_keyword(session, text, country, language)
        session.add(IntentKeyword(intent_id=intent.id, keyword_id=keyword.id, is_primary=(idx == 0)))
    session.commit()


def generate_deterministic_seed_intents(
    session: Session,
    *,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    categories: list[Category],
    country: str,
    language: str,
    max_intents: int,
) -> list[Intent]:
    """Zero-cost intents straight from the catalog — no AI, confidence 1.0.
    Always runs first; AI expansion (below) only adds on top of this."""
    intents: list[Intent] = []
    seen_topics: set[str] = set()

    for category in categories:
        if len(intents) >= max_intents:
            break
        topic = (category.name or "").strip()
        if not topic or topic.lower() in seen_topics:
            continue
        seen_topics.add(topic.lower())

        stable_intent = get_or_create_stable_intent(
            session, store_id=store_id, topic=topic, country=country, language=language, intent_type=topic
        )
        intent = Intent(
            store_id=store_id,
            research_run_id=research_run_id,
            stable_intent_id=stable_intent.id,
            topic=topic,
            category=topic,
            country=country,
            language=language,
            confidence=1.0,
            source=IntentSource.deterministic_catalog,
        )
        session.add(intent)
        session.commit()
        session.refresh(intent)
        _attach_keywords(session, intent, [topic], country, language)
        intents.append(intent)

    return intents


async def run_intent_expansion_agent(
    *,
    session: Session,
    router: ModelRouter,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    categories: list[Category],
    products: list[Product],
    fallback_page_titles: list[str] | None = None,
    identity_context: str | None = None,
    country: str,
    language: str,
    max_intents: int,
    already_generated: int,
) -> list[Intent]:
    """AI-assisted expansion on top of the deterministic seeds — grounded in
    the catalog summary it's given, never inventing catalog facts. Only the
    search-intent framing (topic/stage/demand/keyword phrasing) is AI
    judgment; that's enrichment, not fact, same as store_classification.

    fallback_page_titles: when the crawler's URL-pattern page classifier
    didn't tag anything as product/category (common on Salla/Zid-style
    stores — seen on real test stores), categories/products end up empty
    and there is nothing to seed from. Rather than expanding from nothing,
    fall back to raw page titles/H1s already captured in page_observations
    — still real crawled facts, just not bucketed by page type.

    identity_context: a 4th, lowest-priority fallback tier — used only when
    categories, products, AND fallback_page_titles are all empty (a fully
    blocked/empty crawl). Built by the orchestrator from a web-search-
    resolved StoreIdentity, so there is still a real, non-fabricated basis
    to seed intents from even when nothing at all could be crawled.
    """
    remaining_budget = max_intents - already_generated
    if remaining_budget <= 0:
        return []

    catalog_lines = [f"- تصنيف: {c.name}" for c in categories[:60] if c.name]
    catalog_lines += [f"- منتج: {p.name}" for p in products[:60] if p.name]
    if not catalog_lines and fallback_page_titles:
        catalog_lines = [f"- صفحة: {title}" for title in fallback_page_titles[:60] if title]
    if not catalog_lines and identity_context:
        catalog_lines = [f"- {line}" for line in identity_context.splitlines() if line.strip()]
    store_facts = "\n".join(catalog_lines) or "(لا توجد بيانات كتالوج)"

    messages = INTENT_EXPANSION_PROMPT.render(
        store_facts=store_facts,
        max_intents=str(remaining_budget),
        target_language=language_display_name(language),
    )

    response = await router.execute(
        session=session,
        task_type="intent_expansion",
        messages=messages,
        research_run_id=research_run_id,
        agent_run_id=agent_run_id,
        prompt_name=INTENT_EXPANSION_PROMPT.name,
        prompt_version=INTENT_EXPANSION_PROMPT.version,
        schema_version=INTENT_EXPANSION_PROMPT.schema_version,
        response_schema=IntentExpansionResult,
    )

    if response.parsed is None or response.execution_id is None:
        return []

    result = IntentExpansionResult.model_validate(response.parsed)

    intents: list[Intent] = []
    for suggestion in result.intents[:remaining_budget]:
        stable_intent = get_or_create_stable_intent(
            session,
            store_id=store_id,
            topic=suggestion.topic,
            country=country,
            language=language,
            intent_type=suggestion.category,
        )
        intent = Intent(
            store_id=store_id,
            research_run_id=research_run_id,
            stable_intent_id=stable_intent.id,
            topic=suggestion.topic,
            category=suggestion.category,
            commercial_stage=suggestion.commercial_stage,
            country=country,
            language=language,
            estimated_demand=suggestion.estimated_demand,
            confidence=suggestion.confidence,
            source=IntentSource.ai_expansion,
        )
        session.add(intent)
        session.commit()
        session.refresh(intent)
        _attach_keywords(session, intent, suggestion.keywords, country, language)

        evidence = Evidence(
            store_id=store_id,
            research_run_id=research_run_id,
            source_type=EvidenceSourceType.ai_execution,
            source_id=response.execution_id,
            confidence=suggestion.confidence,
            summary=f"Intent suggested: '{suggestion.topic}'",
        )
        session.add(evidence)
        session.commit()

        intents.append(intent)

    return intents
