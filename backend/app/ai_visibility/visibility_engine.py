import asyncio
import re
import uuid
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.ai_visibility.surfaces import AISurface, resolve_configured_surfaces
from app.core.evaluation_mode import EvaluationMode
from app.core.storage import RawArtifactStore
from app.core.urls import normalize_hostname
from app.models.ai_visibility import AIVisibilityObservation, PromptFamily, PromptVariant
from app.models.catalog import Brand, Product
from app.models.competitor import Competitor
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.intent import Intent
from app.providers.ai.base import AIMessage, AIProviderError, AIRole
from app.providers.ai.router import ModelRouter

URL_PATTERN = re.compile(r"https?://[^\s)\]},،؛]+")

# Kept as a thin backward-compatible alias — surfaces.py (Part F.5-2) is now
# the source of truth for provider/model pairing.
resolve_configured_engines = resolve_configured_surfaces


def _get_brand(session: Session, store_id: uuid.UUID) -> Brand | None:
    return session.exec(select(Brand).where(Brand.store_id == store_id)).first()


def _find_replayable_observation(
    session: Session,
    *,
    store_id: uuid.UUID,
    stable_intent_id: uuid.UUID | None,
    surface: str,
    repetition_index: int,
) -> AIVisibilityObservation | None:
    """Part H1 (post-G-B directive) — real prior probes for this exact
    (store, stable_intent, surface) triple, across any prior research_run,
    ordered most-recent-first. repetition_index picks a *different* real
    historical sample per slot (0 -> most recent, 1 -> the one before that,
    ...) rather than replaying the same single observation into every
    repetition slot, which would trivially show 100% stability and defeat
    the point of a stability metric. None (never a synthesized observation)
    when fewer real historical samples exist than repetition_index+1 —
    stable_intent_id must exist too, since a run-scoped intent_id can't be
    matched across runs."""
    if stable_intent_id is None:
        return None
    candidates = session.exec(
        select(AIVisibilityObservation)
        .where(AIVisibilityObservation.store_id == store_id)
        .where(AIVisibilityObservation.stable_intent_id == stable_intent_id)
        .where(AIVisibilityObservation.surface == surface)
        .where(AIVisibilityObservation.replayed_from_observation_id.is_(None))  # type: ignore[union-attr]
        .order_by(AIVisibilityObservation.observed_at.desc())  # type: ignore[arg-type]
    ).all()
    if repetition_index >= len(candidates):
        return None
    return candidates[repetition_index]


def detect_competitors_mentioned(text: str, competitors: list[Competitor]) -> list[str]:
    """Same programmatic substring matching as detect_mention, applied to
    known competitor domains/names instead of our own brand (Part F.5-6)."""
    lower_text = text.lower()
    mentioned = []
    for competitor in competitors:
        candidates = [competitor.domain, competitor.name]
        if any(c.strip() and c.lower() in lower_text for c in candidates):
            mentioned.append(competitor.domain)
    return mentioned


def detect_products_mentioned(text: str, products: list[Product]) -> list[str]:
    lower_text = text.lower()
    return [p.name for p in products if p.name.strip() and p.name.lower() in lower_text]


def _intent_id_for_variant(session: Session, variant: PromptVariant) -> uuid.UUID | None:
    family = session.get(PromptFamily, variant.prompt_family_id)
    return family.intent_id if family else None


def _stable_intent_id_for_intent(session: Session, intent_id: uuid.UUID) -> uuid.UUID | None:
    intent = session.get(Intent, intent_id)
    return intent.stable_intent_id if intent else None


def detect_mention(text: str, brand: Brand | None) -> tuple[bool, int | None]:
    """Programmatic entity matching against the raw model response — never
    another AI call judging the first one (PRD section 71: the LLM only
    produces text, extraction is the deterministic fact-finder)."""
    if brand is None:
        return False, None

    candidates = [brand.name, *brand.aliases]
    lower_text = text.lower()
    positions = [pos for pos in (lower_text.find(c.lower()) for c in candidates if c.strip()) if pos >= 0]
    if not positions:
        return False, None
    return True, min(positions)


def extract_links(text: str, client_hostname: str) -> tuple[list[str], list[str], list[str]]:
    """Returns (all citation URLs, domains matching the store's own
    hostname, every distinct domain cited) found in the raw response text.
    cited_domains (Part F.5-6) is the broader set — which domains an AI
    surface cites at all for this prompt, ours or a competitor's — feeding
    cross-surface competitor discovery same as SERP results already do."""
    urls = [u.rstrip(".,؛؟?!") for u in URL_PATTERN.findall(text)]
    normalized_client = normalize_hostname(client_hostname) if client_hostname else ""
    all_domains = sorted({hostname for u in urls if (hostname := urlparse(u).hostname)})
    linked_domains = [d for d in all_domains if normalized_client and normalize_hostname(d) == normalized_client]
    return urls, linked_domains, all_domains


def _persist_observation_and_evidence(
    session: Session,
    *,
    store_id: uuid.UUID,
    intent_id: uuid.UUID,
    stable_intent_id: uuid.UUID | None,
    variant_id: uuid.UUID,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    ai_execution_id: uuid.UUID | None,
    surface: AISurface,
    country: str,
    language: str,
    repetition_index: int,
    mentioned: bool,
    position: int | None,
    competitors_mentioned: list[str],
    products_mentioned: list[str],
    citations: list[str],
    linked_domains: list[str],
    cited_domains: list[str],
    raw_artifact_uri: str | None,
    replayed_from_observation_id: uuid.UUID | None,
) -> AIVisibilityObservation:
    observation = AIVisibilityObservation(
        store_id=store_id,
        intent_id=intent_id,
        stable_intent_id=stable_intent_id,
        prompt_variant_id=variant_id,
        research_run_id=research_run_id,
        agent_run_id=agent_run_id,
        ai_execution_id=ai_execution_id,
        surface=surface.surface,
        provider=surface.provider,
        model=surface.model,
        search_enabled=surface.search_enabled,
        grounding_enabled=surface.grounding_enabled,
        citations_available=surface.citations_available,
        country=country,
        language=language,
        repetition_index=repetition_index,
        mentioned=mentioned,
        mention_position=position,
        competitors_mentioned=competitors_mentioned,
        products_mentioned=products_mentioned,
        citations=citations,
        linked_domains=linked_domains,
        cited_domains=cited_domains,
        raw_artifact_uri=raw_artifact_uri,
        replayed_from_observation_id=replayed_from_observation_id,
    )
    session.add(observation)
    session.commit()
    session.refresh(observation)

    summary = (
        f"{surface.surface} mentioned the store at position {position}"
        if mentioned
        else f"{surface.surface} did not mention the store"
    )
    if replayed_from_observation_id is not None:
        summary = f"[replay] {summary}"
    session.add(
        Evidence(
            store_id=store_id,
            research_run_id=research_run_id,
            source_type=EvidenceSourceType.ai_visibility_observation,
            source_id=observation.id,
            confidence=1.0,
            summary=summary,
        )
    )
    session.commit()
    return observation


async def _execute_one_probe(
    router: ModelRouter,
    semaphore: asyncio.Semaphore,
    session: Session,
    surface: AISurface,
    variant: PromptVariant,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
):
    """Part H5 — the semaphore bounds how many real AI calls are in flight
    at once (AI_MAX_CONCURRENCY), independent of SERP's own limit. Returns
    None instead of raising on a failed/unconfigured provider so gather()
    never needs return_exceptions — one failed probe is an ordinary result
    here, not an exception to unwind. router.execute_single's only await is
    the provider call itself; its post-await bookkeeping (_log) is pure
    sync session writes with no further awaits, so sharing one `session`
    across these concurrently-gathered calls is safe (Part H7) — the writes
    never actually interleave, only the network waits do."""
    async with semaphore:
        try:
            return await router.execute_single(
                session=session,
                provider_name=surface.provider,
                model=surface.model,
                task_type="ai_visibility_probe",
                messages=[AIMessage(role=AIRole.user, content=variant.text)],
                research_run_id=research_run_id,
                agent_run_id=agent_run_id,
            )
        except (AIProviderError, RuntimeError):
            # RuntimeError covers "provider not configured" (e.g. a key
            # removed mid-run); AIProviderError covers real API failures.
            # Either way, one failed probe shouldn't stop the rest of the
            # matrix.
            return None


async def run_ai_visibility_agent(
    *,
    session: Session,
    router: ModelRouter,
    store_id: uuid.UUID,
    store_url: str,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    prompt_variants: list[PromptVariant],
    surfaces: list[AISurface],
    country: str,
    language: str,
    repetitions: int,
    storage: RawArtifactStore | None = None,
    evaluation_mode: EvaluationMode = EvaluationMode.live,
    max_concurrency: int = 1,
) -> list[AIVisibilityObservation]:
    """The AI Test Matrix: prompt × surface × repetition (PRD section 20,
    extended by Part F.5 to explicit consumer surfaces — chatgpt/gemini/
    claude, see app/ai_visibility/surfaces.py — rather than raw
    provider/model pairs). Every cell is an independent real sample — no
    caching, no fallback (execute_single, not execute) — because the point
    is comparing surfaces against each other, and a stable/unstable mention
    pattern across repetitions is itself the signal (stability metric,
    Part C4).

    Part H1 (post-G-B directive): when evaluation_mode is replay, no new AI
    call is made at all — each cell reuses a real prior probe for the same
    (store, stable_intent, surface) if one exists (_find_replayable_observation),
    skipping the cell entirely (never inventing data) if none does. The
    caller decides the mode; this function never silently falls back from
    live to replay or vice versa.

    Part H5 (post-G-B directive): live cells fire their real AI calls
    concurrently (bounded by max_concurrency, i.e. Settings.ai_max_concurrency)
    instead of one prompt×surface×repetition at a time — replay cells need
    no such change since they involve no I/O at all.
    """
    brand = _get_brand(session, store_id)
    client_hostname = urlparse(store_url).hostname or ""
    competitors = session.exec(select(Competitor).where(Competitor.store_id == store_id)).all()
    products = session.exec(select(Product).where(Product.store_id == store_id)).all()

    observations: list[AIVisibilityObservation] = []
    live_cells: list[tuple[PromptVariant, uuid.UUID, uuid.UUID | None, AISurface, int]] = []

    for variant in prompt_variants:
        intent_id = _intent_id_for_variant(session, variant)
        if intent_id is None:
            continue
        stable_intent_id = _stable_intent_id_for_intent(session, intent_id)

        for surface in surfaces:
            for repetition_index in range(repetitions):
                if evaluation_mode == EvaluationMode.replay:
                    source = _find_replayable_observation(
                        session,
                        store_id=store_id,
                        stable_intent_id=stable_intent_id,
                        surface=surface.surface,
                        repetition_index=repetition_index,
                    )
                    if source is None:
                        continue
                    observation = _persist_observation_and_evidence(
                        session,
                        store_id=store_id,
                        intent_id=intent_id,
                        stable_intent_id=stable_intent_id,
                        variant_id=variant.id,
                        research_run_id=research_run_id,
                        agent_run_id=agent_run_id,
                        ai_execution_id=None,
                        surface=surface,
                        country=country,
                        language=language,
                        repetition_index=repetition_index,
                        mentioned=source.mentioned,
                        position=source.mention_position,
                        competitors_mentioned=source.competitors_mentioned,
                        products_mentioned=source.products_mentioned,
                        citations=source.citations,
                        linked_domains=source.linked_domains,
                        cited_domains=source.cited_domains,
                        raw_artifact_uri=source.raw_artifact_uri,
                        replayed_from_observation_id=source.id,
                    )
                    observations.append(observation)
                    continue

                live_cells.append((variant, intent_id, stable_intent_id, surface, repetition_index))

    if not live_cells:
        return observations

    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    responses = await asyncio.gather(
        *(
            _execute_one_probe(router, semaphore, session, surface, variant, research_run_id, agent_run_id)
            for variant, _, _, surface, _ in live_cells
        )
    )

    for (variant, intent_id, stable_intent_id, surface, repetition_index), response in zip(live_cells, responses):
        if response is None:
            continue

        mentioned, position = detect_mention(response.text, brand)
        competitors_mentioned = detect_competitors_mentioned(response.text, competitors)
        products_mentioned = detect_products_mentioned(response.text, products)
        citations, linked_domains, cited_domains = extract_links(response.text, client_hostname)

        raw_artifact_uri = None
        if storage is not None and response.text:
            raw_artifact_uri = storage.put_text(
                f"ai-visibility/{store_id}/{surface.surface}", response.text, content_type="text/plain"
            )

        observation = _persist_observation_and_evidence(
            session,
            store_id=store_id,
            intent_id=intent_id,
            stable_intent_id=stable_intent_id,
            variant_id=variant.id,
            research_run_id=research_run_id,
            agent_run_id=agent_run_id,
            ai_execution_id=response.execution_id,
            surface=surface,
            country=country,
            language=language,
            repetition_index=repetition_index,
            mentioned=mentioned,
            position=position,
            competitors_mentioned=competitors_mentioned,
            products_mentioned=products_mentioned,
            citations=citations,
            linked_domains=linked_domains,
            cited_domains=cited_domains,
            raw_artifact_uri=raw_artifact_uri,
            replayed_from_observation_id=None,
        )
        observations.append(observation)

    return observations
