import json

from app.crawler import platform_catalog
from app.crawler.fetch import FetchError, FetchResult
from app.crawler.security import CrawlSecurityPolicy

POLICY = CrawlSecurityPolicy(max_response_bytes=1_000_000, request_timeout_seconds=5, user_agent="TestBot/1.0")


def _result(text: str, content_type: str = "text/html") -> FetchResult:
    return FetchResult(url="https://example.com", status_code=200, content_type=content_type, text=text)


async def test_detect_platform_early_returns_platform_from_homepage_html(monkeypatch):
    async def fake_safe_fetch(url, policy):
        return _result('<html><body class="shopify-features"></body></html>')

    monkeypatch.setattr(platform_catalog, "safe_fetch", fake_safe_fetch)
    assert await platform_catalog.detect_platform_early("https://shop.example.com", POLICY) == "shopify"


async def test_detect_platform_early_returns_none_on_fetch_failure(monkeypatch):
    async def fake_safe_fetch(url, policy):
        raise FetchError("blocked")

    monkeypatch.setattr(platform_catalog, "safe_fetch", fake_safe_fetch)
    assert await platform_catalog.detect_platform_early("https://example.com", POLICY) is None


async def test_detect_platform_early_returns_none_when_no_marker_matches(monkeypatch):
    async def fake_safe_fetch(url, policy):
        return _result("<html><body>plain store, no known platform</body></html>")

    monkeypatch.setattr(platform_catalog, "safe_fetch", fake_safe_fetch)
    assert await platform_catalog.detect_platform_early("https://example.com", POLICY) is None


async def test_discover_shopify_catalog_urls_builds_product_and_collection_urls(monkeypatch):
    calls: list[str] = []

    async def fake_safe_fetch(url, policy):
        calls.append(url)
        if "/products.json" in url and "page=1" in url:
            return _result(json.dumps({"products": [{"handle": "a"}, {"handle": "b"}]}), "application/json")
        if "/products.json" in url:
            return _result(json.dumps({"products": []}), "application/json")
        if "/collections.json" in url:
            return _result(json.dumps({"collections": [{"handle": "c1"}]}), "application/json")
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(platform_catalog, "safe_fetch", fake_safe_fetch)
    urls = await platform_catalog.discover_shopify_catalog_urls("https://shop.example.com", POLICY)

    assert "https://shop.example.com/products/a" in urls
    assert "https://shop.example.com/products/b" in urls
    assert "https://shop.example.com/collections/c1" in urls
    # A partial page (2 < SHOPIFY_PRODUCTS_PAGE_SIZE) stops pagination after page 1.
    assert sum(1 for c in calls if "/products.json" in c) == 1


async def test_discover_shopify_catalog_urls_stops_on_fetch_failure(monkeypatch):
    async def fake_safe_fetch(url, policy):
        raise FetchError("not found")

    monkeypatch.setattr(platform_catalog, "safe_fetch", fake_safe_fetch)
    urls = await platform_catalog.discover_shopify_catalog_urls("https://shop.example.com", POLICY)
    assert urls == []


async def test_discover_shopify_catalog_urls_stops_on_malformed_json(monkeypatch):
    async def fake_safe_fetch(url, policy):
        return _result("not json", "application/json")

    monkeypatch.setattr(platform_catalog, "safe_fetch", fake_safe_fetch)
    urls = await platform_catalog.discover_shopify_catalog_urls("https://shop.example.com", POLICY)
    assert urls == []


async def test_discover_alternate_sitemap_urls_tries_paths_in_order_and_stops_at_first_hit(monkeypatch):
    attempted: list[str] = []

    async def fake_fetch_sitemap_urls(sitemap_url, policy):
        attempted.append(sitemap_url)
        if sitemap_url.endswith("/product-sitemap.xml"):
            return ["https://store.example.com/p/1"]
        return []

    urls = await platform_catalog.discover_alternate_sitemap_urls(
        "https://store.example.com", POLICY, fake_fetch_sitemap_urls
    )

    assert urls == ["https://store.example.com/p/1"]
    # Tried in declared order, stopped as soon as one path returned results —
    # /sitemap/products.xml (the last, lower-priority path) was never tried.
    assert attempted == [
        "https://store.example.com/sitemap_index.xml",
        "https://store.example.com/sitemap-products.xml",
        "https://store.example.com/product-sitemap.xml",
    ]


async def test_discover_alternate_sitemap_urls_returns_empty_when_none_match(monkeypatch):
    async def fake_fetch_sitemap_urls(sitemap_url, policy):
        return []

    urls = await platform_catalog.discover_alternate_sitemap_urls(
        "https://store.example.com", POLICY, fake_fetch_sitemap_urls
    )
    assert urls == []
