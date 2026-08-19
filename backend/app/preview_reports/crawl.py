"""Minimal, bounded crawl for a PreviewReport — homepage + sitemap-derived
category/product pages, capped small (see Settings.preview_crawler_*). This
is a thin wrapper over the existing app.crawler.crawl.crawl_store(), which
is already DB-free and already degrades sitemap/nav-discovery/bot-block
failures internally (see its own docstring/comments) — nothing here
reimplements that. It exists only to pin down the smaller preview-specific
budget so this stage stays a few seconds out of the ~30-45s report target,
not to add new crawl logic.

Does not catch crawl_store's own exceptions — a genuinely unexpected
failure here should surface as a failed report stage (see
app.preview_reports.orchestration), not be silently swallowed into an
empty page list."""

from app.core.config import Settings
from app.crawler.crawl import CrawledPage, crawl_store


async def crawl_for_preview(store_url: str, settings: Settings) -> list[CrawledPage]:
    return await crawl_store(
        store_url,
        max_pages=settings.preview_crawler_max_pages,
        max_depth=settings.preview_crawler_max_depth,
        request_timeout_seconds=settings.crawler_request_timeout_seconds,
        max_response_bytes=settings.crawler_max_response_bytes,
        user_agent=settings.crawler_user_agent,
        max_concurrency=settings.preview_crawler_max_concurrency,
        overall_timeout_seconds=settings.preview_crawler_overall_timeout_seconds,
        stop_when_sufficient=True,
        min_pages_for_sufficiency=settings.preview_crawler_min_pages_for_sufficiency,
        max_playwright_fallbacks=settings.preview_crawler_max_playwright_fallbacks,
    )


def pick_home_page(pages: list[CrawledPage]) -> CrawledPage | None:
    return next((page for page in pages if page.page_type == "home"), None)
