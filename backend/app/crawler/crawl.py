import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from app.crawler.extract import PageFacts, extract_product_facts, looks_like_category_page
from app.crawler.platform_catalog import detect_platform_early, discover_alternate_sitemap_urls, discover_shopify_catalog_urls
from app.crawler.playwright_fetch import fetch_with_playwright
from app.crawler.robots_sitemap import fetch_robots, fetch_sitemap_urls
from app.crawler.security import CrawlSecurityPolicy, looks_like_bot_block
from app.crawler.subprocess_fetch import PageFetchFailed, fetch_and_extract_in_subprocess

CATEGORY_SEGMENTS = ("/category/", "/categories/", "/collections/", "/c/")
PRODUCT_SEGMENTS = ("/product/", "/products/", "/p/", "/item/")
CONTENT_SEGMENTS = ("/blog/", "/article/", "/articles/", "/faq", "/news/")
LOW_VALUE_SEGMENTS = ("/login", "/cart", "/search", "/account", "/filter", "/tag/", "?page=", "?sort=")
BUSINESS_INFO_SEGMENTS = ("/shipping", "/delivery", "/contact", "/about", "التوصيل", "الشحن", "تواصل")


def classify_page_type(url: str) -> str:
    path = urlparse(url).path.lower()
    if path in ("", "/"):
        return "home"
    if any(seg in path for seg in PRODUCT_SEGMENTS):
        return "product"
    if any(seg in path for seg in CATEGORY_SEGMENTS):
        return "category"
    if any(seg in path for seg in CONTENT_SEGMENTS):
        return "content"
    return "other"


@dataclass
class CrawledPage:
    facts: PageFacts
    page_type: str
    product: dict | None
    html: str


async def crawl_store(
    base_url: str,
    *,
    max_pages: int,
    max_depth: int,
    request_timeout_seconds: float,
    max_response_bytes: int,
    user_agent: str,
    rate_limit_delay_seconds: float = 0.5,
    max_concurrency: int = 1,
    overall_timeout_seconds: float | None = None,
    stop_when_sufficient: bool = False,
    min_pages_for_sufficiency: int = 6,
    max_playwright_fallbacks: int = 5,
    diagnostics: dict | None = None,
) -> list[CrawledPage]:
    """Baseline crawl: sitemap.xml -> robots.txt -> nav discovery, bounded by
    max_pages/max_depth, respecting robots.txt and rate limits. Extraction is
    entirely deterministic (app.crawler.extract) — no AI in this function.

    diagnostics: optional dict the caller passes in and this function
    mutates in place — kept as an out-parameter rather than changing the
    return type, so every existing caller/test that does
    `pages = await crawl_store(...)` keeps working unmodified. Currently
    only ever sets diagnostics["blocked_detected"] = True the moment any
    page fetch looks like a bot-block (see app.crawler.security.
    looks_like_bot_block) — lets the orchestrator distinguish "genuinely
    small/empty site" from "actively blocked" for Store.catalog_status.
    """
    if diagnostics is None:
        diagnostics = {}
    diagnostics.setdefault("blocked_detected", False)
    playwright_fallbacks_used = 0
    policy = CrawlSecurityPolicy(
        max_response_bytes=max_response_bytes,
        request_timeout_seconds=request_timeout_seconds,
        user_agent=user_agent,
    )
    site_hostname = urlparse(base_url).hostname

    robots, sitemap_urls_from_robots = await fetch_robots(base_url, policy)

    seed_sitemaps = sitemap_urls_from_robots or [base_url.rstrip("/") + "/sitemap.xml"]
    discovered: list[str] = []
    for sitemap_url in seed_sitemaps:
        discovered.extend(await fetch_sitemap_urls(sitemap_url, policy))

    # Generic sitemap/nav-link discovery silently fails on JS-rendered
    # storefronts and on sitemap paths that don't match the one guessed
    # default above. When the homepage reveals a known platform, read that
    # platform's own catalog structure directly instead of relying solely on
    # the guess — Shopify exposes a public, unauthenticated /products.json
    # and /collections.json; Salla/Zid have no equivalent public API, so a
    # widened sitemap search is the realistic alternative there.
    platform = await detect_platform_early(base_url, policy)
    if platform == "shopify" and robots.can_fetch(user_agent, base_url.rstrip("/") + "/products.json"):
        discovered.extend(await discover_shopify_catalog_urls(base_url, policy))
    elif platform in ("salla", "zid") and not discovered:
        discovered.extend(await discover_alternate_sitemap_urls(base_url, policy, fetch_sitemap_urls))

    # A real store's sitemap can list thousands of URLs (locale variants,
    # full historical catalog, etc.) — every entry is a depth-0 seed, so
    # max_depth alone can't bound this. Without a cap, a single large
    # sitemap turns "crawl up to max_pages pages" into "attempt fetches
    # against the store's entire sitemap," which scales with catalog size
    # instead of the page budget the caller actually asked for. A generous
    # multiplier still gives plenty of headroom to skip dupes/redirects/
    # failures and still reach max_pages.
    discovered = discovered[: max_pages * 20]

    def priority(url: str) -> tuple[int, int]:
        lower = url.lower()
        if lower.rstrip("/") == base_url.lower().rstrip("/"):
            return (0, len(url))
        if any(segment in lower for segment in LOW_VALUE_SEGMENTS):
            return (9, len(url))
        if any(segment in lower for segment in CATEGORY_SEGMENTS):
            return (1, len(url))
        if any(segment in lower for segment in PRODUCT_SEGMENTS):
            return (2, len(url))
        if any(segment in lower for segment in BUSINESS_INFO_SEGMENTS):
            return (3, len(url))
        if any(segment in lower for segment in CONTENT_SEGMENTS):
            return (7, len(url))
        return (5, len(url))

    # The homepage is always first; sitemap order is usually chronological,
    # not useful for understanding a store. Rank commercial structure first.
    discovered = sorted({base_url, *discovered}, key=priority)

    # queue holds (url, depth) — depth 0 is the seed set (sitemap or homepage)
    queue: list[tuple[str, int]] = [(u, 0) for u in (discovered or [base_url])]
    seen: set[str] = set()  # queued URLs already dispatched (pre-fetch dedup)
    processed: set[str] = set()  # final post-redirect URLs already turned into a page (post-fetch dedup)
    pages: list[CrawledPage] = []

    # Overall wall-clock deadline for the whole crawl, independent of any
    # single fetch/extraction's own timeout — belt-and-suspenders after
    # Round 3 live validation surfaced multiple distinct ways a real-world
    # page could keep a crawl running far longer than any individual step's
    # nominal bound. A partial crawl (whatever pages were collected before
    # the deadline) is always usable; an unbounded one is not.
    deadline = time.monotonic() + (
        overall_timeout_seconds if overall_timeout_seconds is not None else max(120.0, request_timeout_seconds * max_pages)
    )

    def enough_information() -> bool:
        if len(pages) < min_pages_for_sufficiency:
            return False
        categories = sum(page.page_type == "category" for page in pages)
        products = sum(page.page_type == "product" for page in pages)
        has_home = any(page.page_type == "home" for page in pages)
        return has_home and categories >= 3 and products >= 2

    idx = 0
    sufficient = False
    while idx < len(queue) and len(pages) < max_pages and not sufficient:
        if time.monotonic() > deadline:
            break
        batch: list[tuple[str, int]] = []
        while idx < len(queue) and len(batch) < max(1, max_concurrency):
            url, depth = queue[idx]
            idx += 1
            if url in seen or depth > max_depth or not robots.can_fetch(user_agent, url):
                continue
            seen.add(url)
            batch.append((url, depth))
        if not batch:
            continue

        # The whole per-page operation (URL safety validation, HTTP GET
        # with redirects, and BeautifulSoup/lxml extraction) runs in a
        # genuine child process, killed outright at the OS level if it
        # exceeds its deadline. Round 3 crawler hardening proved, with
        # timestamped evidence from real store crawls, that neither half
        # of this can be reliably bounded in-process: a CPU-bound lxml
        # parse can hold the GIL long enough that even asyncio.wait_for's
        # own timeout callback never gets scheduled to fire, and a stalled
        # DNS lookup ignored every configured timeout on its own path for
        # nearly 20 minutes. Only OS-level process termination is
        # guaranteed to work regardless of what's blocking internally. See
        # fetch_worker.py / subprocess_fetch.py.
        async def fetch_candidate(item: tuple[str, int]):
            nonlocal playwright_fallbacks_used
            url, depth = item
            try:
                result = await fetch_and_extract_in_subprocess(
                    url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes
                )
                if looks_like_bot_block(result.html, result.status_code) and playwright_fallbacks_used < max_playwright_fallbacks:
                    # A 2xx response that's actually a JS-rendered
                    # challenge interstitial — the status-code check alone
                    # can't catch this, only the page content can.
                    diagnostics["blocked_detected"] = True
                    playwright_fallbacks_used += 1
                    try:
                        result = await fetch_with_playwright(
                            url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes
                        )
                    except PageFetchFailed:
                        return None
                return result, depth
            except PageFetchFailed as exc:
                if not looks_like_bot_block(exc.html, exc.status_code):
                    return None
                diagnostics["blocked_detected"] = True
                if playwright_fallbacks_used >= max_playwright_fallbacks:
                    return None
                playwright_fallbacks_used += 1
                try:
                    result = await fetch_with_playwright(
                        url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes
                    )
                    return result, depth
                except PageFetchFailed:
                    return None

        fetched = await asyncio.gather(*(fetch_candidate(item) for item in batch))
        for fetched_item in fetched:
            if len(pages) >= max_pages:
                break
            if fetched_item is None:
                continue
            result, depth = fetched_item

        # Different queued URLs can redirect to the same final destination
        # (old paths, /ar vs / variants, trailing slashes...). `seen` only
        # catches repeats of the exact original URL — dedup on the resolved
        # URL separately, or the same page gets a fresh observation once per
        # distinct path that happens to redirect to it.
            canonical_key = (result.facts.canonical or result.url).split("#", 1)[0].rstrip("/")
            if canonical_key in processed:
                continue
            processed.add(canonical_key)

            if result.content_type and "html" not in result.content_type:
                continue

            facts = result.facts
            page_type = classify_page_type(result.url)
            product = extract_product_facts(facts.json_ld)
            if product and page_type == "other":
                page_type = "product"
            elif page_type == "other" and looks_like_category_page(facts.json_ld):
                page_type = "category"

            pages.append(CrawledPage(facts=facts, page_type=page_type, product=product, html=result.html))

            if depth < max_depth:
                ranked_links = sorted(facts.internal_links, key=priority)
                for link in ranked_links:
                    if link not in seen:
                        queue.append((link, depth + 1))

            if stop_when_sufficient and enough_information():
                sufficient = True
                break
            if len(pages) >= max_pages:
                break

        await asyncio.sleep(rate_limit_delay_seconds)

    return pages
