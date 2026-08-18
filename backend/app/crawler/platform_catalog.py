"""Platform-aware seed discovery for the crawl queue.

app.crawler.platform_detection already fingerprints Shopify/Salla/Zid/
WooCommerce deterministically from raw HTML, but until now it only ran
*after* a crawl finished, purely to label Store.platform_hint — it never
influenced what got crawled. Generic link/sitemap discovery silently fails
on JS-rendered storefronts (no nav links in the raw HTML) and on sitemap
paths that don't match the one guessed default (/sitemap.xml), producing
near-empty crawls (1 page, 0 products) that then poison classification and
everything downstream.

This module adds seed URLs from a platform's own known catalog structure
when one is detected — Shopify's public /products.json and /collections.json
REST endpoints (well-documented, no auth), and a widened sitemap search for
Salla/Zid (which have no public per-store catalog API). Every function here
only produces plain URL strings that get merged into crawl.py's existing
`discovered` list; the fetch loop, JSON-LD extraction, page-type
classification, and persistence are completely unaware of how a URL was
discovered and require no changes.
"""

import json

from app.crawler.fetch import FetchError, safe_fetch
from app.crawler.platform_detection import detect_platform_from_html
from app.crawler.security import CrawlSecurityPolicy

SHOPIFY_PRODUCTS_PAGE_SIZE = 250
SHOPIFY_MAX_CATALOG_PAGES = 8  # up to 2000 products; crawl.py's own discovered[:max_pages*20] cap still applies after this

# Salla and Zid are hosted SaaS platforms with no documented public,
# unauthenticated catalog API per store (unlike Shopify's /products.json) —
# a widened sitemap search is the realistic, low-risk alternative: read-only,
# standard sitemap protocol, reusing the already-existing fetch_sitemap_urls
# (which already degrades gracefully to [] on a 404 or unparseable body).
# These specific paths are reasoned, not confirmed against live Salla/Zid
# HTML — worth spot-checking against real stores and adjusting if needed.
ALTERNATE_SITEMAP_PATHS = (
    "/sitemap_index.xml",
    "/sitemap-products.xml",
    "/product-sitemap.xml",
    "/sitemap/products.xml",
)


async def detect_platform_early(base_url: str, policy: CrawlSecurityPolicy) -> str | None:
    """One lightweight homepage fetch, purely to decide crawl *strategy*
    before the real crawl loop starts. The main loop still fetches the
    homepage again for real extraction — a deliberate small duplicate
    request, traded for not restructuring crawl_store()'s queue/seen/
    processed bookkeeping. Returns None on any fetch failure, exactly like
    detect_platform_from_html returns None when no marker matches — an
    undetected platform is always the honest default, never a guess."""
    try:
        result = await safe_fetch(base_url, policy)
    except FetchError:
        return None
    return detect_platform_from_html(result.text)


async def discover_shopify_catalog_urls(base_url: str, policy: CrawlSecurityPolicy) -> list[str]:
    """Reads Shopify's public /products.json and /collections.json REST
    endpoints directly. These only tell us which product/collection URLs
    exist — extract_product_facts() still runs its own schema.org JSON-LD
    extraction against each page once it's actually fetched, so nothing
    downstream of seeding needs to trust this feed's contents, only its
    URLs."""
    root = base_url.rstrip("/")
    urls: list[str] = []

    for page in range(1, SHOPIFY_MAX_CATALOG_PAGES + 1):
        try:
            result = await safe_fetch(f"{root}/products.json?limit={SHOPIFY_PRODUCTS_PAGE_SIZE}&page={page}", policy)
            payload = json.loads(result.text)
        except (FetchError, ValueError):
            # Not every Shopify store exposes this endpoint (merchant-
            # disabled, or the store isn't actually Shopify despite the
            # HTML marker match) — fail closed to whatever was already
            # found, never raise past the caller.
            break
        products = payload.get("products") if isinstance(payload, dict) else None
        if not isinstance(products, list) or not products:
            break
        for product in products:
            handle = product.get("handle") if isinstance(product, dict) else None
            if handle:
                urls.append(f"{root}/products/{handle}")
        if len(products) < SHOPIFY_PRODUCTS_PAGE_SIZE:
            break

    try:
        result = await safe_fetch(f"{root}/collections.json?limit={SHOPIFY_PRODUCTS_PAGE_SIZE}&page=1", policy)
        payload = json.loads(result.text)
        collections = payload.get("collections") if isinstance(payload, dict) else None
        if isinstance(collections, list):
            for collection in collections:
                handle = collection.get("handle") if isinstance(collection, dict) else None
                if handle:
                    urls.append(f"{root}/collections/{handle}")
    except (FetchError, ValueError):
        pass

    return urls


async def discover_alternate_sitemap_urls(base_url: str, policy: CrawlSecurityPolicy, fetch_sitemap_urls_fn) -> list[str]:
    """Tries a short list of common alternate sitemap paths, stopping at the
    first one that yields anything. fetch_sitemap_urls_fn is injected (not
    imported directly) purely so tests can stub it without needing a real
    fetch — pass app.crawler.robots_sitemap.fetch_sitemap_urls in
    production. Honest limitation: best-effort, not a guarantee — if none of
    these paths exist either, this returns [] and the caller falls back to
    today's existing homepage-only discovery, never worse than before."""
    root = base_url.rstrip("/")
    for path in ALTERNATE_SITEMAP_PATHS:
        found = await fetch_sitemap_urls_fn(root + path, policy)
        if found:
            return found
    return []
