"""Deterministic e-commerce platform fingerprinting (Part G-B5).

Store.platform_hint was a documented field ("detected later by the
crawler") that nothing ever actually set — every store in the G-A benchmark
came back with platform_hint=None. Fixed here with plain substring markers
against raw crawled HTML: CDN hostnames, framework-injected JS globals, and
generator meta tags that each platform emits itself — exact, stable
strings, not a guess. AI is deliberately not used as a first (or even
fallback) source: these markers are unambiguous where they exist, and a
store matching none of them keeps platform_hint=None (honest 'unknown',
same 'unavailable != guessed' principle as everywhere else in this project)
rather than an LLM inventing a platform name that looks plausible.
"""

PLATFORM_SIGNATURES: dict[str, tuple[str, ...]] = {
    "shopify": (
        "cdn.shopify.com",
        "myshopify.com",
        "shopify.shop",
        "shopify-features",
        "content=\"shopify\"",
    ),
    "salla": (
        "cdn.salla.sa",
        "salla.sa",
        "salla.config",
        "salla-boot",
    ),
    "zid": (
        "cdn.zid.store",
        "zid.store",
        "zid.config",
        "zid-theme",
    ),
    "woocommerce": (
        "wp-content/plugins/woocommerce",
        "woocommerce-page",
        "wc-ajax",
        "content=\"woocommerce",
    ),
}
"""Registry, not a hardcoded if/elif chain — same rationale as
OPPORTUNITY_DETECTORS/AI_VISIBILITY_SURFACES elsewhere: adding a new
platform (Magento, PrestaShop, ...) is one new entry, no engine changes.
Checked in declared order; the first platform with any matching marker
wins."""


def detect_platform_from_html(html: str) -> str | None:
    """Case-insensitive substring match against one page's raw HTML. Cheap
    enough to run on every crawled page (see detect_platform_from_pages)."""
    if not html:
        return None
    lowered = html.lower()
    for platform, markers in PLATFORM_SIGNATURES.items():
        if any(marker in lowered for marker in markers):
            return platform
    return None


def detect_platform_from_pages(html_pages: list[str]) -> str | None:
    """First page (in crawl order) that reveals a platform signature wins —
    checking every page (not just the homepage) matters because some
    platforms' markers only show up on templated product/category pages,
    not necessarily the landing page."""
    for html in html_pages:
        platform = detect_platform_from_html(html)
        if platform is not None:
            return platform
    return None
