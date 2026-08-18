import json
import uuid
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.ai_visibility.surfaces import AISurface
from app.ai_visibility.visibility_engine import (
    _find_replayable_observation,
    _get_brand,
    _persist_observation_and_evidence,
    detect_competitors_mentioned,
    detect_mention,
    detect_products_mentioned,
    extract_links,
)
from app.core.evaluation_mode import EvaluationMode
from app.core.storage import RawArtifactStore
from app.core.urls import normalize_hostname
from app.models.ai_visibility import AIVisibilityObservation, PromptVariant
from app.models.catalog import Product
from app.models.competitor import Competitor
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.intent import Intent, IntentKeyword, IntentSource, Keyword
from app.models.measurement import MeasurementBaseline
from app.models.serp import SerpExecution, SerpExecutionStatus, SerpObservation
from app.models.stable_intent import StableIntent
from app.models.store import Store
from app.providers.ai.base import AIMessage, AIProviderError, AIRole
from app.providers.ai.router import ModelRouter
from app.providers.search.base import SearchProvider, SearchProviderError, SearchRequest
from app.providers.search.pricing import estimate_search_cost_usd


def _find_client_result(results, client_hostname: str):
    normalized_client = normalize_hostname(client_hostname)
    for item in results:
        if normalize_hostname(item.domain) == normalized_client:
            return item
    return None


def _get_or_create_run_intent(
    session: Session, store: Store, research_run_id: uuid.UUID, stable_intent: StableIntent, cache: dict[uuid.UUID, Intent]
) -> Intent:
    """One lightweight Intent row per stable intent per run, purely to
    satisfy SerpObservation/AIVisibilityObservation's existing intent_id FK
    — stable_intent_id is what actually carries identity across runs (Part
    F.5-0). Cached per call so a stable intent that appears in both the
    Control Set's queries and prompts doesn't get two Intent rows."""
    if stable_intent.id in cache:
        return cache[stable_intent.id]
    existing = session.exec(
        select(Intent)
        .where(Intent.research_run_id == research_run_id)
        .where(Intent.stable_intent_id == stable_intent.id)
    ).first()
    if existing is not None:
        cache[stable_intent.id] = existing
        return existing

    intent = Intent(
        store_id=store.id, research_run_id=research_run_id, stable_intent_id=stable_intent.id,
        topic=stable_intent.canonical_topic, country=stable_intent.country, language=stable_intent.language,
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    cache[stable_intent.id] = intent
    return intent


async def remeasure_control_set(
    *,
    session: Session,
    search_provider: SearchProvider,
    router: ModelRouter,
    store: Store,
    recommendation_id: uuid.UUID,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    ai_surfaces: list[AISurface],
    storage: RawArtifactStore | None = None,
    evaluation_mode: EvaluationMode = EvaluationMode.live,
) -> None:
    """Part F.5-11 — monitoring must not depend on a recommendation's target
    stable intents *happening* to be among this run's Discovery-regenerated
    intents (they usually aren't — AI expansion produces a fresh, different
    top-N list every run). Instead, actively re-issue the exact keyword/
    prompt captured at baseline time for each target stable intent, once
    per run, so measure_visibility_for_intents always has something fresh
    to find.

    Part Q4 — the SERP half is already mode-safe for free: `search_provider`
    is injected by app.providers.search.get_search_provider, which already
    swaps in ReplaySearchProvider for replay mode before this function ever
    sees it. The AI-surface half had no equivalent protection — router
    (app.providers.ai.get_router) always holds real provider adapters
    regardless of mode (mode-awareness is each *caller's* job, per
    run_ai_visibility_agent's own pattern) — so without evaluation_mode
    threaded through here, every monitoring pass would fire real OpenAI/
    Anthropic/Google calls even during ordinary replay-mode development.
    Fixed the same way run_ai_visibility_agent does: replay mode reuses a
    real prior observation for the same (store, stable_intent, surface) via
    _find_replayable_observation, never calls the router at all.
    """
    baseline = session.exec(
        select(MeasurementBaseline).where(MeasurementBaseline.recommendation_id == recommendation_id)
    ).first()
    if baseline is None:
        return

    client_hostname = urlparse(store.url).hostname or ""
    run_intent_cache: dict[uuid.UUID, Intent] = {}

    for target_query in baseline.target_queries:
        stable_intent_id_str = target_query.get("stable_intent_id")
        if stable_intent_id_str is None:
            # Pre-Part-F.5-0 baseline row never backfilled (migration
            # 1c522554b6c4 covers the normal case) — nothing to key off,
            # skip rather than crash the whole monitoring pass over it.
            continue
        stable_intent_id = uuid.UUID(stable_intent_id_str)
        already_measured = session.exec(
            select(SerpObservation)
            .where(SerpObservation.research_run_id == research_run_id)
            .where(SerpObservation.stable_intent_id == stable_intent_id)
        ).first()
        if already_measured is not None:
            continue

        keyword_id = target_query.get("keyword_id")
        keyword = session.get(Keyword, uuid.UUID(keyword_id)) if keyword_id else None
        stable_intent = session.get(StableIntent, stable_intent_id)
        if keyword is None or stable_intent is None:
            continue

        intent = _get_or_create_run_intent(session, store, research_run_id, stable_intent, run_intent_cache)
        existing_link = session.exec(
            select(IntentKeyword).where(IntentKeyword.intent_id == intent.id).where(IntentKeyword.keyword_id == keyword.id)
        ).first()
        if existing_link is None:
            session.add(IntentKeyword(intent_id=intent.id, keyword_id=keyword.id, is_primary=True))
            session.commit()

        request = SearchRequest(keyword=keyword.text, country=keyword.country, language=keyword.language)
        response = None
        status = SerpExecutionStatus.success
        error: str | None = None
        try:
            response = await search_provider.search(request)
        except SearchProviderError as exc:
            status = SerpExecutionStatus.error
            error = str(exc)

        session.add(
            SerpExecution(
                research_run_id=research_run_id, agent_run_id=agent_run_id, provider=search_provider.underlying_provider_name,
                keyword=keyword.text, country=keyword.country, language=keyword.language,
                cost_usd=estimate_search_cost_usd(search_provider.underlying_provider_name) if response is not None else None,
                latency_ms=response.latency_ms if response else None, status=status, error=error,
            )
        )
        session.commit()
        if response is None:
            continue

        client_result = _find_client_result(response.results, client_hostname)
        raw_artifact_uri = None
        if storage is not None and response.raw is not None:
            raw_artifact_uri = storage.put_text(
                f"serp/{store.id}", json.dumps(response.raw, ensure_ascii=False), content_type="application/json"
            )
        observation = SerpObservation(
            store_id=store.id, intent_id=intent.id, stable_intent_id=stable_intent_id, keyword_id=keyword.id,
            research_run_id=research_run_id, agent_run_id=agent_run_id, country=keyword.country,
            language=keyword.language, results=[r.model_dump() for r in response.results],
            client_rank=client_result.rank if client_result else None,
            client_url=client_result.url if client_result else None,
            raw_artifact_uri=raw_artifact_uri,
        )
        session.add(observation)
        session.commit()
        session.refresh(observation)
        session.add(
            Evidence(
                store_id=store.id, research_run_id=research_run_id, source_type=EvidenceSourceType.serp_observation,
                source_id=observation.id, confidence=1.0,
                summary=f"Control-set re-check for '{keyword.text}': rank {observation.client_rank}",
            )
        )
        session.commit()

    if not ai_surfaces:
        return

    brand = _get_brand(session, store.id)
    competitors = session.exec(select(Competitor).where(Competitor.store_id == store.id)).all()
    products = session.exec(select(Product).where(Product.store_id == store.id)).all()

    prompts_by_variant: dict[str, str] = {
        tp["prompt_variant_id"]: tp["stable_intent_id"]
        for tp in baseline.target_prompts
        if tp.get("prompt_variant_id") and tp.get("stable_intent_id")
    }

    for prompt_variant_id_str, stable_intent_id_str in prompts_by_variant.items():
        variant = session.get(PromptVariant, uuid.UUID(prompt_variant_id_str))
        stable_intent = session.get(StableIntent, uuid.UUID(stable_intent_id_str))
        if variant is None or stable_intent is None:
            continue
        intent = _get_or_create_run_intent(session, store, research_run_id, stable_intent, run_intent_cache)

        for surface in ai_surfaces:
            already_measured = session.exec(
                select(AIVisibilityObservation)
                .where(AIVisibilityObservation.research_run_id == research_run_id)
                .where(AIVisibilityObservation.prompt_variant_id == variant.id)
                .where(AIVisibilityObservation.surface == surface.surface)
            ).first()
            if already_measured is not None:
                continue

            if evaluation_mode == EvaluationMode.replay:
                # Part Q4 — never call the real router in replay mode; reuse
                # a real prior probe for this exact (store, stable_intent,
                # surface) if one exists, skip this cell entirely otherwise
                # (never invent data), same contract as run_ai_visibility_agent.
                source = _find_replayable_observation(
                    session, store_id=store.id, stable_intent_id=stable_intent.id,
                    surface=surface.surface, repetition_index=0,
                )
                if source is None:
                    continue
                _persist_observation_and_evidence(
                    session, store_id=store.id, intent_id=intent.id, stable_intent_id=stable_intent.id,
                    variant_id=variant.id, research_run_id=research_run_id, agent_run_id=agent_run_id,
                    ai_execution_id=None, surface=surface, country=stable_intent.country,
                    language=stable_intent.language, repetition_index=0, mentioned=source.mentioned,
                    position=source.mention_position, competitors_mentioned=source.competitors_mentioned,
                    products_mentioned=source.products_mentioned, citations=source.citations,
                    linked_domains=source.linked_domains, cited_domains=source.cited_domains,
                    raw_artifact_uri=source.raw_artifact_uri, replayed_from_observation_id=source.id,
                )
                continue

            try:
                response = await router.execute_single(
                    session=session, provider_name=surface.provider, model=surface.model,
                    task_type="ai_visibility_probe", messages=[AIMessage(role=AIRole.user, content=variant.text)],
                    research_run_id=research_run_id, agent_run_id=agent_run_id,
                )
            except (AIProviderError, RuntimeError):
                continue

            mentioned, position = detect_mention(response.text, brand)
            competitors_mentioned = detect_competitors_mentioned(response.text, competitors)
            products_mentioned = detect_products_mentioned(response.text, products)
            citations, linked_domains, cited_domains = extract_links(response.text, client_hostname)

            observation = AIVisibilityObservation(
                store_id=store.id, intent_id=intent.id, stable_intent_id=stable_intent.id,
                prompt_variant_id=variant.id, research_run_id=research_run_id, agent_run_id=agent_run_id,
                ai_execution_id=response.execution_id, surface=surface.surface, provider=surface.provider,
                model=surface.model, search_enabled=surface.search_enabled, grounding_enabled=surface.grounding_enabled,
                citations_available=surface.citations_available, country=stable_intent.country,
                language=stable_intent.language, repetition_index=0, mentioned=mentioned, mention_position=position,
                competitors_mentioned=competitors_mentioned, products_mentioned=products_mentioned,
                citations=citations, linked_domains=linked_domains, cited_domains=cited_domains,
            )
            session.add(observation)
            session.commit()
            session.refresh(observation)

            summary = (
                f"Control-set re-check: {surface.surface} mentioned the store"
                if mentioned
                else f"Control-set re-check: {surface.surface} did not mention the store"
            )
            session.add(
                Evidence(
                    store_id=store.id, research_run_id=research_run_id,
                    source_type=EvidenceSourceType.ai_visibility_observation, source_id=observation.id,
                    confidence=1.0, summary=summary,
                )
            )
            session.commit()
