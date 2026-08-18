import uuid
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.core.storage import RawArtifactStore
from app.crawler.crawl import crawl_store
from app.crawler.extract import EXTRACTOR_VERSION
from app.crawler.locale_detection import detect_locale, resolve_locale_with_ai_fallback
from app.crawler.platform_detection import detect_platform_from_pages
from app.models.base import utcnow
from app.models.catalog import Brand, Category, Page, Product
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.observation import PageObservation
from app.models.store import Store
from app.prompts.store_classification import STORE_CLASSIFICATION_PROMPT
from app.providers.ai.router import ModelRouter
from app.schemas.store_classification import StoreClassification
from app.store_intelligence.catalog_resolution import canonical_store_url, resolve_product_category


def _get_or_create_page(session: Session, store_id: uuid.UUID, url: str, page_type: str) -> Page:
    existing = session.exec(select(Page).where(Page.store_id == store_id).where(Page.url == url)).first()
    if existing:
        return existing
    page = Page(store_id=store_id, url=url, page_type=page_type)
    session.add(page)
    session.commit()
    session.refresh(page)
    return page


def _to_float(value: object) -> float | None:
    try:
        return float(value) if value else None
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _upsert_product(session: Session, store_id: uuid.UUID, page: Page, product_facts: dict) -> Product:
    price = _to_float(product_facts.get("price"))
    original_price = _to_float(product_facts.get("original_price"))

    products = session.exec(select(Product).where(Product.store_id == store_id)).all()
    canonical_page_url = canonical_store_url(page.url)
    existing = next((item for item in products if canonical_store_url(item.url) == canonical_page_url), None)
    if existing:
        existing.name = product_facts.get("name") or existing.name
        existing.price = price
        existing.original_price = original_price
        existing.currency = product_facts.get("currency")
        existing.availability = product_facts.get("availability")
        existing.sku = product_facts.get("sku") or existing.sku
        existing.rating = product_facts.get("rating")
        existing.review_count = _to_int(product_facts.get("review_count"))
        existing.image_url = product_facts.get("image_url") or existing.image_url
        existing.last_seen_at = utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    product = Product(
        store_id=store_id,
        name=product_facts.get("name") or page.url,
        url=page.url,
        price=price,
        original_price=original_price,
        currency=product_facts.get("currency"),
        availability=product_facts.get("availability"),
        sku=product_facts.get("sku"),
        rating=product_facts.get("rating"),
        review_count=_to_int(product_facts.get("review_count")),
        image_url=product_facts.get("image_url"),
    )
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


def _upsert_category(session: Session, store_id: uuid.UUID, name: str, url: str) -> Category:
    """Part R1 (Round 1 remediation) — Category is a *canonical entity*
    (current best-known facts about the store), not an immutable
    observation. PageObservation rows already capture the immutable,
    per-crawl history (Part R1's canonical-vs-observation split); this row
    must track the latest extraction, exactly like _upsert_product already
    does for Product.name/price/etc. Before this fix, a Category row
    created from a buggy extraction (e.g. a scraped <title> instead of
    <h1> — the Q3 bug) stayed wrong forever on every subsequent re-crawl,
    since only a fresh URL ever created a new row; an existing URL match
    returned the stale row untouched. That is exactly what left
    extra.com permanently stuck at 0 accepted intents in Round 1: its
    Category rows predated the H1-over-title fix and were never refreshed
    by the re-crawl that used the corrected extractor."""
    existing = session.exec(select(Category).where(Category.store_id == store_id).where(Category.url == url)).first()
    if existing:
        if name and name != existing.name:
            existing.name = name
            session.add(existing)
            session.commit()
            session.refresh(existing)
        return existing
    category = Category(store_id=store_id, name=name, url=url)
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def _extract_brand_candidates(json_ld: list[dict]) -> list[str]:
    """schema.org Organization/Brand name, or Product.brand — a deterministic
    fact, not an AI guess. This is what powers brand-mention detection in
    the AI Visibility Engine later; without it there's nothing to match
    against a model's response text."""
    names: list[str] = []
    for entry in json_ld:
        raw_types = entry.get("@type")
        types = [raw_types] if isinstance(raw_types, str) else (raw_types or [])
        if "Organization" in types or "Brand" in types:
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        if "Product" in types or "ProductGroup" in types:
            brand = entry.get("brand")
            if isinstance(brand, dict) and isinstance(brand.get("name"), str):
                names.append(brand["name"].strip())
            elif isinstance(brand, str) and brand.strip():
                names.append(brand.strip())
    return names


def _guess_brand_name_from_domain(base_url: str) -> str:
    domain = urlparse(base_url).hostname or ""
    return domain.removeprefix("www.").split(".")[0].replace("-", " ").title()


def _upsert_brand(session: Session, store_id: uuid.UUID, name: str, base_url: str) -> Brand:
    """One brand per store for V1 (multi-brand stores are a future
    refinement) — later distinct spellings become aliases instead of
    separate rows, since Entity Resolution needs to match all of them.

    Part R1 (Round 1 remediation) — canonical-field staleness applies here
    too, not just to Category. `name` here always comes from real JSON-LD
    (Organization/Brand/Product.brand — see _extract_brand_candidates),
    a strictly more authoritative signal than the domain-derived guess
    _ensure_fallback_brand falls back to when no page ever carried
    structured brand data. If the canonical row still holds exactly that
    guessed name unmodified, a later crawl that finds a real brand name
    must promote it to canonical — not just tack it onto aliases forever
    — while still never overwriting an already-real name (which would
    just flip-flop arbitrarily on a genuine multi-brand store, an
    accepted V1 limitation, not this bug)."""
    existing = session.exec(select(Brand).where(Brand.store_id == store_id)).first()
    if existing:
        if name.lower() != existing.name.lower():
            looks_like_unpromoted_guess = existing.name == _guess_brand_name_from_domain(base_url)
            if looks_like_unpromoted_guess:
                if existing.name not in existing.aliases:
                    existing.aliases = [*existing.aliases, existing.name]
                existing.name = name
                session.add(existing)
                session.commit()
                session.refresh(existing)
            elif name not in existing.aliases:
                existing.aliases = [*existing.aliases, name]
                session.add(existing)
                session.commit()
                session.refresh(existing)
        return existing

    brand = Brand(store_id=store_id, name=name, aliases=[])
    session.add(brand)
    session.commit()
    session.refresh(brand)
    return brand


def _ensure_fallback_brand(session: Session, store_id: uuid.UUID, base_url: str) -> None:
    """If no page ever carried Organization/Brand/Product.brand JSON-LD
    (happens on some Salla/Zid-style stores, same gap we hit with
    categories/products), derive a rough brand name from the domain rather
    than leaving mention-detection with nothing to match against."""
    existing = session.exec(select(Brand).where(Brand.store_id == store_id)).first()
    if existing is not None:
        return

    domain = urlparse(base_url).hostname or ""
    guessed_name = _guess_brand_name_from_domain(base_url)
    if guessed_name:
        session.add(Brand(store_id=store_id, name=guessed_name, aliases=[domain]))
        session.commit()


async def run_crawl_agent(
    *,
    session: Session,
    storage: RawArtifactStore,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    base_url: str,
    max_pages: int,
    max_depth: int,
    request_timeout_seconds: float,
    max_response_bytes: int,
    user_agent: str,
    router: ModelRouter | None = None,
    max_concurrency: int = 1,
    overall_timeout_seconds: float | None = None,
    stop_when_sufficient: bool = False,
    min_pages_for_sufficiency: int = 6,
    max_playwright_fallbacks: int = 5,
    diagnostics: dict | None = None,
) -> list[PageObservation]:
    """Crawl + deterministic extraction + persistence. Almost entirely
    programmatic — the only AI call is the Part R2-F1 locale fallback
    below, and only when the deterministic multi-signal pass is
    inconclusive; `router=None` (the default) skips it entirely and
    leaves the store's locale explicitly `unresolved` rather than
    guessing. One page_observation per crawled page (not one row per
    field), per the Evidence Ledger design.

    diagnostics: optional out-parameter dict, passed straight through to
    crawl_store() — see its docstring. Kept as an out-param here too
    rather than changing this function's return type, so every existing
    caller doing `observations = await run_crawl_agent(...)` keeps working
    unmodified."""
    if diagnostics is None:
        diagnostics = {}

    crawled_pages = await crawl_store(
        base_url,
        max_pages=max_pages,
        max_depth=max_depth,
        request_timeout_seconds=request_timeout_seconds,
        max_response_bytes=max_response_bytes,
        user_agent=user_agent,
        max_concurrency=max_concurrency,
        overall_timeout_seconds=overall_timeout_seconds,
        stop_when_sufficient=stop_when_sufficient,
        min_pages_for_sufficiency=min_pages_for_sufficiency,
        max_playwright_fallbacks=max_playwright_fallbacks,
        diagnostics=diagnostics,
    )

    observations: list[PageObservation] = []

    for crawled in crawled_pages:
        raw_uri = storage.put_text(f"stores/{store_id}/runs/{research_run_id}/pages", crawled.html)

        page = _get_or_create_page(session, store_id, crawled.facts.url, crawled.page_type)

        if crawled.page_type == "product" and crawled.product:
            _upsert_product(session, store_id, page, crawled.product)
        elif crawled.page_type == "category":
            # Part Q3 — <title> commonly carries a "Category | Site Name"
            # suffix (e.g. books.toscrape.com's "Academic | Books to
            # Scrape - Sandbox"), which is exactly a scraped-page-title
            # shape once it becomes an Intent topic (app.intent.quality
            # now hard-rejects it, but the real fix is not extracting it as
            # a category name in the first place). h1 is on-page DOM
            # content — the actual heading a visitor sees — and matches
            # this project's own extraction hierarchy (DOM before
            # metadata); falls back to title only when no h1 exists.
            category_name = crawled.facts.h1 or crawled.facts.title or page.url
            _upsert_category(session, store_id, category_name, page.url)

        for brand_name in _extract_brand_candidates(crawled.facts.json_ld):
            _upsert_brand(session, store_id, brand_name, base_url)

        observation = PageObservation(
            store_id=store_id,
            research_run_id=research_run_id,
            agent_run_id=agent_run_id,
            page_id=page.id,
            source_url=crawled.facts.url,
            source="crawler",
            extractor_version=EXTRACTOR_VERSION,
            raw_artifact_uri=raw_uri,
            normalized_extraction=crawled.facts.to_normalized_dict(),
            extracted_entities={},
        )
        session.add(observation)
        session.commit()
        session.refresh(observation)
        observations.append(observation)

        # Evidence at observation granularity, only for pages that carry a
        # commercial claim worth tracing later (product/category) — not one
        # row per crawled page, and never per field.
        if crawled.page_type in ("product", "category"):
            evidence = Evidence(
                store_id=store_id,
                research_run_id=research_run_id,
                source_type=EvidenceSourceType.page_observation,
                source_id=observation.id,
                confidence=1.0,  # deterministic extraction, not AI inference
                summary=f"{crawled.page_type} page observed: {crawled.facts.title or crawled.facts.url}",
            )
            session.add(evidence)
            session.commit()

    _ensure_fallback_brand(session, store_id, base_url)

    # Category assignment is deliberately delayed until every page in this
    # crawl has been persisted, because product pages are often visited before
    # the category URL they link to. Only observed internal links are used.
    products_by_url = {
        canonical_store_url(product.url): product
        for product in session.exec(select(Product).where(Product.store_id == store_id)).all()
    }
    for observation in observations:
        product = products_by_url.get(canonical_store_url(observation.source_url))
        if product is None:
            continue
        category = resolve_product_category(
            session, product, (observation.normalized_extraction or {}).get("internal_links") or []
        )
        if category is not None and product.category_id != category.id:
            product.category_id = category.id
            session.add(product)
    session.commit()

    # Part G-B5 — deterministic platform fingerprint from the HTML already
    # crawled this run, zero extra requests. Only overwrite a previously
    # detected hint when this run actually found one; a run where no page
    # happened to reveal a marker (e.g. hit fewer pages than usual) must
    # not erase a hint a prior run already established.
    platform_hint = detect_platform_from_pages([c.html for c in crawled_pages])
    if platform_hint is not None:
        store = session.get(Store, store_id)
        if store is not None:
            store.platform_hint = platform_hint
            session.add(store)
            session.commit()

    await _resolve_and_persist_locale(
        session=session,
        store_id=store_id,
        base_url=base_url,
        pages=[c.facts for c in crawled_pages],
        router=router,
        research_run_id=research_run_id,
        agent_run_id=agent_run_id,
    )

    return observations


def _summarize_locale_context_for_ai(pages: list, base_url: str) -> str:
    lines = [f"store URL: {base_url}"]
    for page in pages[:15]:
        lines.append(
            f"- [{page.url}] title={page.title!r} html_lang={page.html_lang!r} "
            f"hreflang={list(page.hreflang.keys())!r} canonical={page.canonical!r}"
        )
    return "\n".join(lines)


async def _resolve_and_persist_locale(
    *,
    session: Session,
    store_id: uuid.UUID,
    base_url: str,
    pages: list,
    router: ModelRouter | None,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
) -> None:
    """Part R2-F1 (Round 2 remediation) — replaces the confirmed-broken
    behavior of leaving Store.country/language NULL forever (which made
    every downstream consumer silently fall back to Settings.serp_default_
    country/language = 'sa'/'ar', regardless of the store's real market).
    Runs on every crawl, refreshing the stored locale exactly like
    platform_hint above — a later, better-signalled crawl should be able
    to correct an earlier unresolved/low-confidence result."""
    result = detect_locale(pages, base_url)
    if result.status == "unresolved" and router is not None:
        result = await resolve_locale_with_ai_fallback(
            result,
            session=session,
            router=router,
            store_id=store_id,
            research_run_id=research_run_id,
            agent_run_id=agent_run_id,
            store_context=_summarize_locale_context_for_ai(pages, base_url),
        )

    store = session.get(Store, store_id)
    if store is None:
        return
    store.country = result.country
    store.language = result.language
    store.market = result.market
    store.locale_confidence = result.confidence
    store.locale_source = result.source
    store.locale_status = result.status
    session.add(store)
    session.commit()


MIN_OBSERVATIONS_FOR_CLASSIFICATION = 3
"""Mirrors the project's existing evidence-count floors — evidence_supported
= len(evidence_ids) >= 2 (recommendation_engine.py), MIN_INTENT_CONFIDENCE =
0.4 (opportunities/detectors.py). business_type is a required field on
StoreClassification, so the model always has to return *some* answer —
without this gate, a near-empty/bot-blocked crawl (0-2 observations) still
produces a plausible-looking but essentially fabricated classification.
Deliberately low: this only screens the degenerate near-zero case, not
"the crawl was merely thin" (crawler_fast_min_pages' own sufficiency floor
of 6 is a separate, higher bar for a different purpose)."""


def has_sufficient_observations_for_classification(observations: list[PageObservation]) -> bool:
    return len(observations) >= MIN_OBSERVATIONS_FOR_CLASSIFICATION


def summarize_observations_for_context(observations: list[PageObservation], limit: int = 40) -> str:
    """Shared by store classification and (Phase 1) identity resolution —
    a compact, real-facts-only summary of whatever the crawler actually
    read, used as grounding context for either AI call."""
    lines: list[str] = []
    for obs in observations[:limit]:
        extraction = obs.normalized_extraction or {}
        lines.append(f"- [{obs.source_url}] title={extraction.get('title')!r} h1={extraction.get('h1')!r}")
    return "\n".join(lines) or "(no pages crawled)"


async def run_store_classification_agent(
    *,
    session: Session,
    router: ModelRouter,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    observations: list[PageObservation],
) -> tuple[StoreClassification | None, uuid.UUID | None]:
    """AI enrichment step — classifies the store based only on the
    deterministic facts already extracted by the crawler. Never invents
    facts; every output is traceable to the ai_executions row via evidence.
    """
    store_facts = summarize_observations_for_context(observations)
    messages = STORE_CLASSIFICATION_PROMPT.render(store_facts=store_facts)

    response = await router.execute(
        session=session,
        task_type="classification",
        messages=messages,
        research_run_id=research_run_id,
        agent_run_id=agent_run_id,
        prompt_name=STORE_CLASSIFICATION_PROMPT.name,
        prompt_version=STORE_CLASSIFICATION_PROMPT.version,
        schema_version=STORE_CLASSIFICATION_PROMPT.schema_version,
        response_schema=StoreClassification,
    )

    if response.parsed is None or response.execution_id is None:
        return None, None

    classification = StoreClassification.model_validate(response.parsed)

    evidence = Evidence(
        store_id=store_id,
        research_run_id=research_run_id,
        source_type=EvidenceSourceType.ai_execution,
        source_id=response.execution_id,
        confidence=classification.confidence,
        summary=f"Store classified as '{classification.business_type}'",
    )
    session.add(evidence)
    session.commit()
    session.refresh(evidence)

    return classification, evidence.id
