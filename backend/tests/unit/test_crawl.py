from app.crawler import crawl as crawl_module
from app.crawler.crawl import crawl_store
from app.crawler.extract import extract_page_facts
from app.crawler.robots_sitemap import RobotFileParser
from app.crawler.subprocess_fetch import FetchedPage

HOME_HTML = """
<html><body>
<a href="/old-a">old path a</a>
<a href="/old-b">old path b</a>
</body></html>
"""

FINAL_HTML = "<html><head><title>Final Page</title></head><body>content</body></html>"


async def test_crawl_dedupes_pages_reached_via_different_redirecting_urls(monkeypatch):
    """Real bug reproduction: two different queued URLs (/old-a, /old-b)
    both redirect to the same final destination. Without dedup on the
    post-redirect URL, this produced one PageObservation per original path
    instead of one per actual page."""

    async def fake_fetch_robots(base_url, policy):
        parser = RobotFileParser()
        parser.parse([])  # matches fetch_robots()'s real "no robots.txt found" behavior: allow-all
        return parser, []

    async def fake_fetch_sitemap_urls(sitemap_url, policy, _depth=0):
        return []

    def _fetched(final_url: str, html: str) -> FetchedPage:
        # Mirrors what fetch_and_extract_in_subprocess really returns —
        # extraction already done, exactly as the real subprocess worker
        # would have produced it for this HTML.
        facts = extract_page_facts(final_url, html, "example.com")
        return FetchedPage(url=final_url, status_code=200, content_type="text/html", html=html, facts=facts)

    async def fake_fetch_and_extract(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        if url == "https://example.com":
            return _fetched(url, HOME_HTML)
        if url in ("https://example.com/old-a", "https://example.com/old-b"):
            # Both redirect to the same final URL — the fetch already
            # resolved the redirect, so result.url differs from the
            # requested url.
            return _fetched("https://example.com/final", FINAL_HTML)
        raise AssertionError(f"unexpected url fetched: {url}")

    async def fake_detect_platform_early(base_url, policy):
        return None

    monkeypatch.setattr(crawl_module, "fetch_robots", fake_fetch_robots)
    monkeypatch.setattr(crawl_module, "fetch_sitemap_urls", fake_fetch_sitemap_urls)
    monkeypatch.setattr(crawl_module, "fetch_and_extract_in_subprocess", fake_fetch_and_extract)
    monkeypatch.setattr(crawl_module, "detect_platform_early", fake_detect_platform_early)

    pages = await crawl_store(
        "https://example.com",
        max_pages=10,
        max_depth=2,
        request_timeout_seconds=5,
        max_response_bytes=1_000_000,
        user_agent="TestBot/1.0",
        rate_limit_delay_seconds=0,
    )

    final_urls = [p.facts.url for p in pages]
    assert final_urls.count("https://example.com/final") == 1
    assert len(pages) == 2  # home + the one deduped final page


async def test_fast_crawl_prioritizes_structure_and_stops_when_evidence_is_sufficient(monkeypatch):
    fetched_urls: list[str] = []

    async def fake_fetch_robots(base_url, policy):
        parser = RobotFileParser()
        parser.parse([])
        return parser, []

    async def fake_fetch_sitemap_urls(sitemap_url, policy, _depth=0):
        return [
            "https://example.com/login",
            "https://example.com/blog/post",
            "https://example.com/products/p1",
            "https://example.com/collections/c3",
            "https://example.com/collections/c1",
            "https://example.com/contact",
            "https://example.com/products/p2",
            "https://example.com/collections/c2",
        ]

    async def fake_fetch_and_extract(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        fetched_urls.append(url)
        html = f"<html><head><title>{url}</title></head><body></body></html>"
        return FetchedPage(
            url=url,
            status_code=200,
            content_type="text/html",
            html=html,
            facts=extract_page_facts(url, html, "example.com"),
        )

    async def fake_detect_platform_early(base_url, policy):
        return None

    monkeypatch.setattr(crawl_module, "fetch_robots", fake_fetch_robots)
    monkeypatch.setattr(crawl_module, "fetch_sitemap_urls", fake_fetch_sitemap_urls)
    monkeypatch.setattr(crawl_module, "fetch_and_extract_in_subprocess", fake_fetch_and_extract)
    monkeypatch.setattr(crawl_module, "detect_platform_early", fake_detect_platform_early)

    pages = await crawl_store(
        "https://example.com",
        max_pages=10,
        max_depth=1,
        request_timeout_seconds=5,
        max_response_bytes=1_000_000,
        user_agent="TestBot/1.0",
        rate_limit_delay_seconds=0,
        max_concurrency=3,
        overall_timeout_seconds=90,
        stop_when_sufficient=True,
        min_pages_for_sufficiency=6,
    )

    assert len(pages) == 6
    assert sum(page.page_type == "category" for page in pages) == 3
    assert sum(page.page_type == "product" for page in pages) == 2
    assert "https://example.com/login" not in fetched_urls
    assert "https://example.com/blog/post" not in fetched_urls


async def test_shopify_platform_detection_seeds_products_and_collections_json(monkeypatch):
    """When the homepage reveals a Shopify signature, discover_shopify_
    catalog_urls' returned product/collection URLs must reach the fetch
    loop exactly like any sitemap-discovered URL — no separate code path."""

    async def fake_fetch_robots(base_url, policy):
        parser = RobotFileParser()
        parser.parse([])
        return parser, []

    async def fake_fetch_sitemap_urls(sitemap_url, policy, _depth=0):
        return []  # sitemap is empty/missing — platform catalog is the only source

    async def fake_detect_platform_early(base_url, policy):
        return "shopify"

    async def fake_discover_shopify_catalog_urls(base_url, policy):
        return ["https://shop.example.com/products/handle-1", "https://shop.example.com/collections/handle-a"]

    fetched_urls: list[str] = []

    async def fake_fetch_and_extract(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        fetched_urls.append(url)
        html = f"<html><head><title>{url}</title></head><body></body></html>"
        return FetchedPage(
            url=url, status_code=200, content_type="text/html", html=html,
            facts=extract_page_facts(url, html, "shop.example.com"),
        )

    monkeypatch.setattr(crawl_module, "fetch_robots", fake_fetch_robots)
    monkeypatch.setattr(crawl_module, "fetch_sitemap_urls", fake_fetch_sitemap_urls)
    monkeypatch.setattr(crawl_module, "fetch_and_extract_in_subprocess", fake_fetch_and_extract)
    monkeypatch.setattr(crawl_module, "detect_platform_early", fake_detect_platform_early)
    monkeypatch.setattr(crawl_module, "discover_shopify_catalog_urls", fake_discover_shopify_catalog_urls)

    pages = await crawl_store(
        "https://shop.example.com",
        max_pages=10, max_depth=1, request_timeout_seconds=5,
        max_response_bytes=1_000_000, user_agent="TestBot/1.0", rate_limit_delay_seconds=0,
    )

    fetched_paths = {p.facts.url for p in pages}
    assert "https://shop.example.com/products/handle-1" in fetched_paths
    assert "https://shop.example.com/collections/handle-a" in fetched_paths
    assert any(p.page_type == "product" for p in pages if p.facts.url.endswith("handle-1"))


async def test_salla_platform_detection_falls_back_to_alternate_sitemaps(monkeypatch):
    """Salla/Zid have no public catalog API — a detected platform with an
    empty default sitemap must trigger the alternate-sitemap search, and
    its URLs must reach the fetch loop the same way."""

    async def fake_fetch_robots(base_url, policy):
        parser = RobotFileParser()
        parser.parse([])
        return parser, []

    async def fake_fetch_sitemap_urls(sitemap_url, policy, _depth=0):
        return []  # the guessed /sitemap.xml yields nothing

    async def fake_detect_platform_early(base_url, policy):
        return "salla"

    async def fake_discover_alternate_sitemap_urls(base_url, policy, fetch_sitemap_urls_fn):
        return ["https://store.example.com/products/handle-2"]

    fetched_urls: list[str] = []

    async def fake_fetch_and_extract(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        fetched_urls.append(url)
        html = f"<html><head><title>{url}</title></head><body></body></html>"
        return FetchedPage(
            url=url, status_code=200, content_type="text/html", html=html,
            facts=extract_page_facts(url, html, "store.example.com"),
        )

    monkeypatch.setattr(crawl_module, "fetch_robots", fake_fetch_robots)
    monkeypatch.setattr(crawl_module, "fetch_sitemap_urls", fake_fetch_sitemap_urls)
    monkeypatch.setattr(crawl_module, "fetch_and_extract_in_subprocess", fake_fetch_and_extract)
    monkeypatch.setattr(crawl_module, "detect_platform_early", fake_detect_platform_early)
    monkeypatch.setattr(crawl_module, "discover_alternate_sitemap_urls", fake_discover_alternate_sitemap_urls)

    pages = await crawl_store(
        "https://store.example.com",
        max_pages=10, max_depth=1, request_timeout_seconds=5,
        max_response_bytes=1_000_000, user_agent="TestBot/1.0", rate_limit_delay_seconds=0,
    )

    fetched_paths = {p.facts.url for p in pages}
    assert "https://store.example.com/products/handle-2" in fetched_paths


async def test_category_json_ld_overrides_url_based_page_type(monkeypatch):
    """classify_page_type() only matches URL path segments — a category page
    whose URL doesn't contain any of those segments (Salla/Zid-style routes)
    must still be recognized as a category via its own CollectionPage
    JSON-LD, symmetric to how Product JSON-LD already overrides "other" to
    "product"."""

    async def fake_fetch_robots(base_url, policy):
        parser = RobotFileParser()
        parser.parse([])
        return parser, []

    async def fake_fetch_sitemap_urls(sitemap_url, policy, _depth=0):
        return ["https://example.com/s/unusual-path"]

    async def fake_detect_platform_early(base_url, policy):
        return None

    category_html = """
    <html><head>
    <script type="application/ld+json">{"@type": "CollectionPage", "name": "Unusual Category"}</script>
    </head><body></body></html>
    """

    async def fake_fetch_and_extract(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        html = category_html if url.endswith("unusual-path") else HOME_HTML
        return FetchedPage(
            url=url, status_code=200, content_type="text/html", html=html,
            facts=extract_page_facts(url, html, "example.com"),
        )

    monkeypatch.setattr(crawl_module, "fetch_robots", fake_fetch_robots)
    monkeypatch.setattr(crawl_module, "fetch_sitemap_urls", fake_fetch_sitemap_urls)
    monkeypatch.setattr(crawl_module, "fetch_and_extract_in_subprocess", fake_fetch_and_extract)
    monkeypatch.setattr(crawl_module, "detect_platform_early", fake_detect_platform_early)

    pages = await crawl_store(
        "https://example.com",
        max_pages=10, max_depth=1, request_timeout_seconds=5,
        max_response_bytes=1_000_000, user_agent="TestBot/1.0", rate_limit_delay_seconds=0,
    )

    unusual = next(p for p in pages if p.facts.url.endswith("unusual-path"))
    assert unusual.page_type == "category"
