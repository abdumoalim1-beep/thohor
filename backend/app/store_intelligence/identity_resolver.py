"""Store identity resolution via web search — deliberately independent of
crawled catalog data. This is the actual fix for stores whose crawl comes
back empty (bot-blocked, JS-rendered nav, etc.): brand name and activity
are often knowable from public web search even when the site itself can't
be read. Crawl-derived classification is the fallback when this fails,
never the other way around.
"""

import asyncio
import uuid

from sqlmodel import Session

from app.models.evidence import Evidence, EvidenceSourceType
from app.models.store import Store
from app.prompts.store_identity import STORE_IDENTITY_PROMPT
from app.providers.ai.base import AIMessage, AIProviderError
from app.providers.ai.router import ModelRouter
from app.schemas.store_identity import StoreIdentity


async def resolve_store_identity(
    *,
    session: Session,
    router: ModelRouter,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    store_url: str,
    crawl_context: str | None = None,
    timeout_seconds: float = 60.0,
) -> tuple[StoreIdentity | None, uuid.UUID | None]:
    """Resolves a store's identity purely from web search. Returns
    (None, None) on any failure or timeout — the caller (orchestrator) is
    responsible for falling back to whatever crawl-derived classification
    exists, never the reverse. crawl_context, when given, is folded in as
    extra grounding for the search (e.g. a page title glimpsed despite an
    otherwise-failed crawl) — it is a hint, not a substitute for the real
    web_search call itself.
    """
    messages: list[AIMessage] = STORE_IDENTITY_PROMPT.render(store_url=store_url)
    if crawl_context:
        messages = [
            *messages[:-1],
            AIMessage(
                role=messages[-1].role,
                content=(
                    f"{messages[-1].content}\n\n"
                    f"معلومات إضافية رُصدت فعليًا من صفحات الموقع (استخدمها كمساعدة فقط، "
                    f"وتحقق منها بالبحث الحقيقي، لا تكتفِ بها):\n{crawl_context}"
                ),
            ),
        ]

    try:
        response = await asyncio.wait_for(
            router.execute(
                session=session,
                task_type="store_identity_resolution",
                messages=messages,
                research_run_id=research_run_id,
                agent_run_id=agent_run_id,
                prompt_name=STORE_IDENTITY_PROMPT.name,
                prompt_version=STORE_IDENTITY_PROMPT.version,
                schema_version=STORE_IDENTITY_PROMPT.schema_version,
                response_schema=StoreIdentity,
                enable_web_search=True,
            ),
            timeout=timeout_seconds,
        )
    except (AIProviderError, RuntimeError, TimeoutError, asyncio.TimeoutError):
        # Same catch shape as visibility_engine._execute_one_probe: a
        # failed/unavailable provider or a timeout is a normal single-call
        # failure here, never something that should propagate and abort
        # the research run.
        return None, None

    if response.parsed is None or response.execution_id is None:
        return None, None

    identity = StoreIdentity.model_validate(response.parsed)

    evidence = Evidence(
        store_id=store_id,
        research_run_id=research_run_id,
        source_type=EvidenceSourceType.ai_execution,
        source_id=response.execution_id,
        confidence=identity.confidence,
        summary=f"Store identity resolved as '{identity.brand_name}' via web search",
    )
    session.add(evidence)

    for source in identity.sources:
        session.add(
            Evidence(
                store_id=store_id,
                research_run_id=research_run_id,
                source_type=EvidenceSourceType.web_search_citation,
                source_id=uuid.uuid5(uuid.NAMESPACE_URL, source.url),
                confidence=identity.confidence,
                summary=f"{source.title} — {source.url}",
            )
        )

    session.commit()
    session.refresh(evidence)

    return identity, evidence.id


def persist_store_identity_fields(store: Store, identity: StoreIdentity, *, source: str) -> None:
    """Sets Store's new identity-tracking fields (Phase 2). Never overrides
    a real crawl-derived locale with an AI guess — only fills country/
    language/market when they're still unresolved, respecting the existing
    locale_status invariant. Business_type/categories deliberately stay
    off Store (see Phase 2) — they live only in the identity agent run's
    findings, same convention as classification.
    """
    from app.models.base import utcnow

    store.identity_source = source
    store.identity_confidence = identity.confidence
    store.last_identity_scan_at = utcnow()

    # country/language are Store's resolved-locale fields (Part R2-F1) —
    # only fill them if the crawler's own locale resolution never ran.
    # identity.market_signals ("محلي"/"إقليمي"/"فاخر"...) is a *business*
    # signal, a different concept from Store.market (a locale/region value
    # set exclusively by app.crawler.locale_detection) — deliberately never
    # written here, to avoid conflating the two.
    if not store.country and identity.country:
        store.country = identity.country
    if not store.language and identity.language:
        store.language = identity.language
