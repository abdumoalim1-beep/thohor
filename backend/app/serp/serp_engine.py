import asyncio
import json
import uuid
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.core.storage import RawArtifactStore
from app.core.urls import normalize_hostname
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.intent import Intent, IntentKeyword, Keyword
from app.models.serp import SerpExecution, SerpExecutionStatus, SerpObservation
from app.providers.search.base import SearchProvider, SearchProviderError, SearchRequest, SearchResponse, SearchResultItem
from app.providers.search.pricing import estimate_search_cost_usd


def _get_primary_keyword(session: Session, intent_id: uuid.UUID) -> Keyword | None:
    link = session.exec(
        select(IntentKeyword).where(IntentKeyword.intent_id == intent_id).where(IntentKeyword.is_primary == True)  # noqa: E712
    ).first()
    if link is None:
        return None
    return session.get(Keyword, link.keyword_id)


def _get_intent_keywords(session: Session, intent_id: uuid.UUID) -> list[Keyword]:
    links = session.exec(select(IntentKeyword).where(IntentKeyword.intent_id == intent_id)).all()
    links.sort(key=lambda link: not link.is_primary)
    return [keyword for link in links if (keyword := session.get(Keyword, link.keyword_id)) is not None]


def _find_client_result(results: list[SearchResultItem], client_hostname: str) -> SearchResultItem | None:
    normalized_client = normalize_hostname(client_hostname)
    for item in results:
        if normalize_hostname(item.domain) == normalized_client:
            return item
    return None


def select_balanced_intents(intents: list[Intent], max_queries: int) -> list[Intent]:
    """Round-robin categories so a large category cannot consume the whole
    measurement budget before smaller product categories are tested."""
    buckets: dict[str, list[Intent]] = {}
    for intent in intents:
        buckets.setdefault(intent.category or "", []).append(intent)
    selected: list[Intent] = []
    while len(selected) < max_queries and any(buckets.values()):
        for bucket in buckets.values():
            if bucket and len(selected) < max_queries:
                selected.append(bucket.pop(0))
    return selected


async def _fetch_one(
    search_provider: SearchProvider,
    semaphore: asyncio.Semaphore,
    request: SearchRequest,
) -> tuple[SearchResponse | None, str | None]:
    """Part H5 — the semaphore bounds how many real requests are in flight
    at once (SERP_MAX_CONCURRENCY), independent of any other provider's
    limit. Returns (response, error) instead of raising so gather() never
    needs return_exceptions — one query failing is an ordinary result here,
    not an exception to unwind."""
    async with semaphore:
        try:
            return await search_provider.search(request), None
        except SearchProviderError as exc:
            return None, str(exc)


async def run_serp_agent(
    *,
    session: Session,
    search_provider: SearchProvider,
    store_id: uuid.UUID,
    store_url: str,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    intents: list[Intent],
    country: str,
    language: str,
    num_results: int,
    max_queries: int,
    storage: RawArtifactStore | None = None,
    max_concurrency: int = 1,
) -> list[SerpObservation]:
    """Measures Google visibility for each intent's primary keyword. One
    SerpObservation per query (not per result) — results holds the raw
    top-N organic list, client_rank/client_url promote the store's own
    position. Every call is logged in serp_executions regardless of
    success/failure (paid external API — usage must always be visible),
    with an estimated cost (Part F.5-12) and, when storage is provided,
    the full raw provider response archived to MinIO (Part F.5-1).

    Part H5 (post-G-B directive): independent queries run concurrently
    (bounded by max_concurrency, i.e. Settings.serp_max_concurrency) instead
    of one at a time — the real network wait (search_provider.search) is
    the only genuinely concurrent phase; every DB write below it stays
    strictly sequential on the single shared `session`, so there is no
    concurrent-session risk despite the concurrent I/O (Part H7)."""
    client_hostname = urlparse(store_url).hostname or ""

    balanced = select_balanced_intents(intents, max_queries)
    keywords_by_intent = [(intent, _get_intent_keywords(session, intent.id)) for intent in balanced]
    keyworded: list[tuple[Intent, Keyword]] = []
    seen_keywords: set[str] = set()
    depth = 0
    while len(keyworded) < max_queries and any(depth < len(keywords) for _, keywords in keywords_by_intent):
        for intent, keywords in keywords_by_intent:
            if depth >= len(keywords) or len(keyworded) >= max_queries:
                continue
            keyword = keywords[depth]
            key = keyword.text.strip().casefold()
            if key and key not in seen_keywords:
                seen_keywords.add(key)
                keyworded.append((intent, keyword))
        depth += 1
    if not keyworded:
        return []

    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    fetches = await asyncio.gather(
        *(
            _fetch_one(
                search_provider, semaphore, SearchRequest(keyword=kw.text, country=country, language=language, num_results=num_results)
            )
            for _, kw in keyworded
        )
    )

    observations: list[SerpObservation] = []

    for (intent, keyword), (response, error) in zip(keyworded, fetches):
        status = SerpExecutionStatus.error if error else SerpExecutionStatus.success
        session.add(
            SerpExecution(
                research_run_id=research_run_id,
                agent_run_id=agent_run_id,
                provider=search_provider.underlying_provider_name,
                keyword=keyword.text,
                country=country,
                language=language,
                cost_usd=estimate_search_cost_usd(search_provider.underlying_provider_name) if response is not None else None,
                latency_ms=response.latency_ms if response else None,
                status=status,
                error=error,
            )
        )
        session.commit()

        if response is None:
            continue

        client_result = _find_client_result(response.results, client_hostname)

        raw_artifact_uri = None
        if storage is not None and response.raw is not None:
            raw_artifact_uri = storage.put_text(
                f"serp/{store_id}", json.dumps(response.raw, ensure_ascii=False), content_type="application/json"
            )

        observation = SerpObservation(
            store_id=store_id,
            intent_id=intent.id,
            stable_intent_id=intent.stable_intent_id,
            keyword_id=keyword.id,
            research_run_id=research_run_id,
            agent_run_id=agent_run_id,
            country=country,
            language=language,
            results=[r.model_dump() for r in response.results],
            client_rank=client_result.rank if client_result else None,
            client_url=client_result.url if client_result else None,
            raw_artifact_uri=raw_artifact_uri,
        )
        session.add(observation)
        session.commit()
        session.refresh(observation)

        summary = (
            f"SERP لـ'{keyword.text}': رتبة المتجر {observation.client_rank}"
            if observation.client_rank
            else f"SERP لـ'{keyword.text}': المتجر غير ظاهر ضمن أفضل {num_results} نتيجة"
        )
        session.add(
            Evidence(
                store_id=store_id,
                research_run_id=research_run_id,
                source_type=EvidenceSourceType.serp_observation,
                source_id=observation.id,
                confidence=1.0,
                summary=summary,
            )
        )
        session.commit()

        observations.append(observation)

    return observations
