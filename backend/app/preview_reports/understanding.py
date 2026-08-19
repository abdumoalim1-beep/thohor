"""Stage 3 (spec) — store understanding for a PreviewReport. Deliberately
NOT the identity_resolver web-search path: the website itself is the
primary identity source here, per the explicit MVP requirement that this
system must not start with AI web search to learn the store name. Name
resolution reuses the exact same deterministic fallback chain
(app.store_intelligence.brand_name_resolution) already used elsewhere,
minus its own web-search tier — that's tier 1 for /signup, but excluded
entirely for PreviewReport.

extract_deterministic_facts() never touches the network or an LLM — pure
in-memory extraction from already-crawled pages. build_understanding()
adds exactly one LLM call on top to organize those facts into simple
prose/JSON; on any failure it falls back to the deterministic facts alone
so a broken LLM call never sinks the whole report (spec: degrade
gracefully, don't fail the report)."""

import asyncio

from sqlmodel import Session

from app.crawler.crawl import CrawledPage
from app.preview_reports.crawl import pick_home_page
from app.prompts.preview_understanding import PREVIEW_UNDERSTANDING_PROMPT
from app.providers.ai.base import AIProviderError
from app.providers.ai.router import ModelRouter
from app.schemas.preview_understanding import PreviewStoreUnderstanding
from app.store_intelligence.brand_name_resolution import registered_hostname, resolve_best_available_name

MAX_PRODUCT_NAMES = 30
MAX_CATEGORY_NAMES = 20
UNDERSTANDING_TIMEOUT_SECONDS = 20.0


def _has_readable_text(value: str) -> bool:
    """Rejects pure numeric/symbol tokens like '#23' — some storefronts
    (observed on Salla) put a raw SKU/variant code in the product JSON-LD
    'name' field instead of a real label. That's not a product name worth
    showing the merchant or handing to query generation as a search
    subject, so it's filtered at the source here rather than downstream —
    every consumer of product_names/category_names (report.store.products,
    the LLM prompt, generate_search_queries) benefits from one filter."""
    return any(ch.isalpha() for ch in value)


def extract_deterministic_facts(pages: list[CrawledPage], store_url: str) -> dict:
    home = pick_home_page(pages)
    home_extraction = home.facts.to_normalized_dict() if home else {}
    brand_name, brand_name_source = resolve_best_available_name(home_extraction=home_extraction, base_url=store_url)

    product_names: list[str] = []
    seen_products: set[str] = set()
    category_names: list[str] = []
    seen_categories: set[str] = set()

    for page in pages:
        if page.page_type == "product" and page.product:
            name = (page.product.get("name") or "").strip()
            key = name.lower()
            if (
                name
                and _has_readable_text(name)
                and key not in seen_products
                and len(product_names) < MAX_PRODUCT_NAMES
            ):
                seen_products.add(key)
                product_names.append(name)
        elif page.page_type == "category":
            label = (page.facts.h1 or page.facts.title or "").strip()
            key = label.lower()
            if (
                label
                and _has_readable_text(label)
                and key not in seen_categories
                and len(category_names) < MAX_CATEGORY_NAMES
            ):
                seen_categories.add(key)
                category_names.append(label)

    return {
        "domain": registered_hostname(store_url),
        "brand_name": brand_name,
        "brand_name_source": brand_name_source,
        "title": home.facts.title if home else None,
        "meta_description": home.facts.meta_description if home else None,
        "og_site_name": home.facts.og_site_name if home else None,
        "og_image": home.facts.og_image if home else None,
        "favicon": home.facts.favicon if home else None,
        "h1": home.facts.h1 if home else None,
        "product_names": product_names,
        "category_names": category_names,
        "pages_crawled": len(pages),
    }


def _fallback_understanding(facts: dict) -> dict:
    return {
        "brand_name": facts["brand_name"],
        "category": facts["category_names"][0] if facts["category_names"] else "",
        "products": facts["product_names"][:10],
    }


async def build_understanding(*, session: Session, router: ModelRouter, facts: dict) -> dict:
    messages = PREVIEW_UNDERSTANDING_PROMPT.render(
        brand_name=facts["brand_name"],
        title=facts.get("title") or "",
        meta_description=facts.get("meta_description") or "",
        h1=facts.get("h1") or "",
        category_names=", ".join(facts["category_names"]) or "لا يوجد",
        product_names=", ".join(facts["product_names"]) or "لا يوجد",
    )
    try:
        response = await asyncio.wait_for(
            router.execute(
                session=session,
                task_type="preview_store_understanding",
                messages=messages,
                prompt_name=PREVIEW_UNDERSTANDING_PROMPT.name,
                prompt_version=PREVIEW_UNDERSTANDING_PROMPT.version,
                schema_version=PREVIEW_UNDERSTANDING_PROMPT.schema_version,
                response_schema=PreviewStoreUnderstanding,
            ),
            timeout=UNDERSTANDING_TIMEOUT_SECONDS,
        )
    except (AIProviderError, RuntimeError, TimeoutError, asyncio.TimeoutError, ValueError):
        return _fallback_understanding(facts)

    if response.parsed is None:
        return _fallback_understanding(facts)

    understanding = PreviewStoreUnderstanding.model_validate(response.parsed)
    return {
        "brand_name": understanding.brand_name.strip() or facts["brand_name"],
        "category": understanding.category.strip(),
        "products": understanding.products or facts["product_names"][:10],
    }
