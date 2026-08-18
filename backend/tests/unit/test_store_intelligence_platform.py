"""Unit-level (no network) coverage for the platform_hint wiring in
run_crawl_agent — crawl_store is monkeypatched so this never hits a real
site, unlike tests/integration/test_store_intelligence.py."""

from app.crawler.crawl import CrawledPage
from app.crawler.extract import PageFacts
from app.crawler import store_intelligence as store_intelligence_module
from app.crawler.store_intelligence import run_crawl_agent
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store

SHOPIFY_HTML = '<html><head><link href="https://cdn.shopify.com/s/files/theme.css"></head><body></body></html>'
PLAIN_HTML = "<html><body><h1>Custom store, no known platform markers</h1></body></html>"


class FakeStorage:
    def put_text(self, key_prefix: str, content: str, content_type: str = "text/html") -> str:
        return f"fake://{key_prefix}"


async def _make_store_and_run(session):
    org = Organization(name="t", slug="t-platform-detection")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    return store, run


async def _run_crawl_with_fake_pages(session, store, run, html_pages: list[str]):
    async def fake_crawl_store(base_url, **kwargs):
        return [
            CrawledPage(facts=PageFacts(url=f"{base_url}/page-{i}"), page_type="home", product=None, html=html)
            for i, html in enumerate(html_pages)
        ]

    store_intelligence_module_crawl_store = store_intelligence_module.crawl_store
    store_intelligence_module.crawl_store = fake_crawl_store
    try:
        return await run_crawl_agent(
            session=session,
            storage=FakeStorage(),
            store_id=store.id,
            research_run_id=run.id,
            agent_run_id=None,
            base_url=store.url,
            max_pages=6,
            max_depth=2,
            request_timeout_seconds=10,
            max_response_bytes=5_000_000,
            user_agent="MersadBot/0.1 (+https://mersad.example/bot)",
        )
    finally:
        store_intelligence_module.crawl_store = store_intelligence_module_crawl_store


async def test_run_crawl_agent_sets_platform_hint_when_signature_found(session):
    store, run = await _make_store_and_run(session)

    await _run_crawl_with_fake_pages(session, store, run, [PLAIN_HTML, SHOPIFY_HTML])

    session.refresh(store)
    assert store.platform_hint == "shopify"


async def test_run_crawl_agent_leaves_platform_hint_none_when_no_signature_found(session):
    store, run = await _make_store_and_run(session)

    await _run_crawl_with_fake_pages(session, store, run, [PLAIN_HTML, PLAIN_HTML])

    session.refresh(store)
    assert store.platform_hint is None


async def test_run_crawl_agent_does_not_erase_previously_detected_hint(session):
    store, run = await _make_store_and_run(session)
    store.platform_hint = "salla"
    session.add(store)
    session.commit()

    # This run's crawled pages happen to reveal no marker at all (e.g. hit
    # fewer/different pages than the run that originally detected it) — the
    # previously established hint must survive, not be wiped to None.
    await _run_crawl_with_fake_pages(session, store, run, [PLAIN_HTML])

    session.refresh(store)
    assert store.platform_hint == "salla"
