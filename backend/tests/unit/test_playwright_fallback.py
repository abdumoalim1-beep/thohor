"""Phase 3 coverage: the Playwright fallback triggers on a bot-block
signature (status code or challenge-page HTML) and never otherwise, and
sets crawl_store's diagnostics["blocked_detected"] correctly — without
ever actually launching a real browser (fetch_with_playwright is
monkeypatched, same technique as the httpx-based fetch is already mocked
in test_crawl.py)."""

from app.crawler import crawl as crawl_module
from app.crawler.crawl import crawl_store
from app.crawler.extract import extract_page_facts
from app.crawler.robots_sitemap import RobotFileParser
from app.crawler.security import looks_like_bot_block
from app.crawler.subprocess_fetch import FetchedPage, PageFetchFailed


def test_looks_like_bot_block_matches_known_status_codes():
    assert looks_like_bot_block(None, 403) is True
    assert looks_like_bot_block(None, 429) is True
    assert looks_like_bot_block(None, 503) is True
    assert looks_like_bot_block(None, 404) is False
    assert looks_like_bot_block(None, 200) is False


def test_looks_like_bot_block_matches_known_html_markers():
    assert looks_like_bot_block("<html><title>Just a moment...</title></html>", 200) is True
    assert looks_like_bot_block("<html>مرحبًا بكم في متجرنا</html>", 200) is False
    assert looks_like_bot_block(None, 200) is False


async def _run_crawl(monkeypatch, *, fetch_and_extract, fetch_with_playwright=None, max_playwright_fallbacks=5):
    async def fake_fetch_robots(base_url, policy):
        parser = RobotFileParser()
        parser.parse([])
        return parser, []

    async def fake_fetch_sitemap_urls(sitemap_url, policy, _depth=0):
        return []

    async def fake_detect_platform_early(base_url, policy):
        return None

    monkeypatch.setattr(crawl_module, "fetch_robots", fake_fetch_robots)
    monkeypatch.setattr(crawl_module, "fetch_sitemap_urls", fake_fetch_sitemap_urls)
    monkeypatch.setattr(crawl_module, "detect_platform_early", fake_detect_platform_early)
    monkeypatch.setattr(crawl_module, "fetch_and_extract_in_subprocess", fetch_and_extract)
    if fetch_with_playwright is not None:
        monkeypatch.setattr(crawl_module, "fetch_with_playwright", fetch_with_playwright)

    diagnostics: dict = {}
    pages = await crawl_store(
        "https://example.com",
        max_pages=10, max_depth=1, request_timeout_seconds=5,
        max_response_bytes=1_000_000, user_agent="TestBot/1.0", rate_limit_delay_seconds=0,
        max_playwright_fallbacks=max_playwright_fallbacks, diagnostics=diagnostics,
    )
    return pages, diagnostics


async def test_403_response_triggers_playwright_fallback_and_succeeds(monkeypatch):
    async def fake_fetch_and_extract(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        raise PageFetchFailed(f"non-success status 403 for {url}", status_code=403)

    playwright_calls = []

    async def fake_fetch_with_playwright(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        playwright_calls.append(url)
        html = "<html><head><title>Real Page</title></head><body>content</body></html>"
        return FetchedPage(url=url, status_code=200, content_type="text/html", html=html, facts=extract_page_facts(url, html, "example.com"))

    pages, diagnostics = await _run_crawl(
        monkeypatch, fetch_and_extract=fake_fetch_and_extract, fetch_with_playwright=fake_fetch_with_playwright
    )

    assert diagnostics["blocked_detected"] is True
    assert len(playwright_calls) >= 1
    assert len(pages) >= 1
    assert pages[0].facts.title == "Real Page"


async def test_playwright_fallback_also_failing_leaves_diagnostics_honest(monkeypatch):
    async def fake_fetch_and_extract(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        raise PageFetchFailed(f"non-success status 403 for {url}", status_code=403)

    async def fake_fetch_with_playwright(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        raise PageFetchFailed(f"playwright also failed for {url}")

    pages, diagnostics = await _run_crawl(
        monkeypatch, fetch_and_extract=fake_fetch_and_extract, fetch_with_playwright=fake_fetch_with_playwright
    )

    assert diagnostics["blocked_detected"] is True
    assert pages == []


async def test_non_bot_block_failure_never_triggers_playwright(monkeypatch):
    playwright_calls = []

    async def fake_fetch_and_extract(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        raise PageFetchFailed(f"non-success status 404 for {url}", status_code=404)

    async def fake_fetch_with_playwright(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        playwright_calls.append(url)
        raise AssertionError("should never be called for a plain 404")

    pages, diagnostics = await _run_crawl(
        monkeypatch, fetch_and_extract=fake_fetch_and_extract, fetch_with_playwright=fake_fetch_with_playwright
    )

    assert diagnostics["blocked_detected"] is False
    assert playwright_calls == []
    assert pages == []


async def test_200_status_challenge_page_html_still_triggers_fallback(monkeypatch):
    """The status-code check alone can't catch a 200 JS-rendered
    interstitial — only inspecting the actual page content can."""

    async def fake_fetch_and_extract(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        html = "<html><title>Just a moment...</title></html>"
        return FetchedPage(url=url, status_code=200, content_type="text/html", html=html, facts=extract_page_facts(url, html, "example.com"))

    async def fake_fetch_with_playwright(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        html = "<html><head><title>Real Page</title></head><body>content</body></html>"
        return FetchedPage(url=url, status_code=200, content_type="text/html", html=html, facts=extract_page_facts(url, html, "example.com"))

    pages, diagnostics = await _run_crawl(
        monkeypatch, fetch_and_extract=fake_fetch_and_extract, fetch_with_playwright=fake_fetch_with_playwright
    )

    assert diagnostics["blocked_detected"] is True
    assert pages[0].facts.title == "Real Page"


async def test_playwright_fallback_cap_is_respected(monkeypatch):
    """Once max_playwright_fallbacks is exhausted, further bot-blocked
    pages are just skipped, not endlessly retried via the expensive path."""
    playwright_calls = []

    async def fake_fetch_and_extract(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        raise PageFetchFailed(f"non-success status 403 for {url}", status_code=403)

    async def fake_fetch_with_playwright(url, site_hostname, user_agent, request_timeout_seconds, max_response_bytes):
        playwright_calls.append(url)
        raise PageFetchFailed("also blocked")

    pages, diagnostics = await _run_crawl(
        monkeypatch, fetch_and_extract=fake_fetch_and_extract, fetch_with_playwright=fake_fetch_with_playwright,
        max_playwright_fallbacks=0,
    )

    assert playwright_calls == []
    assert diagnostics["blocked_detected"] is True
    assert pages == []
