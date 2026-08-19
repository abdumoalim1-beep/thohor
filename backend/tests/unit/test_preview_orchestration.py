"""Stage 12 — the full orchestration job. Covers the two outcomes the
client is ever allowed to observe: status="ready" with one complete
report blob, or status="failed" with an error_message, never a raised
exception left uncaught (the row must never stay stuck at "processing").
Network/AI calls are avoided entirely (no configured providers, crawl
monkeypatched) — this proves the degrade-gracefully wiring, not real
provider behavior, which is covered per-module elsewhere."""

import asyncio

import pytest
from sqlmodel import Session, SQLModel, create_engine

import app.preview_reports.orchestration as orchestration
from app.core.config import Settings
from app.crawler.crawl import CrawledPage
from app.crawler.extract import PageFacts
from app.models.preview_report import PreviewReport
from app.providers.ai.router import ModelRouter


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _make_report(session: Session, store_url: str = "https://zuhoor.sa") -> PreviewReport:
    report = PreviewReport(store_url=store_url, status="processing")
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def test_report_reaches_ready_even_when_search_and_ai_are_fully_unavailable(session, monkeypatch):
    async def fake_crawl(store_url, settings):
        home = PageFacts(url=f"{store_url}/", title="متجر زهور", og_site_name="زهور")
        product = PageFacts(url=f"{store_url}/products/عطر-ورد", title="عطر ورد")
        category = PageFacts(url=f"{store_url}/categories/عطور", h1="عطور نسائية")
        return [
            CrawledPage(facts=home, page_type="home", product=None, html=""),
            CrawledPage(facts=product, page_type="product", product={"name": "عطر ورد"}, html=""),
            CrawledPage(facts=category, page_type="category", product=None, html=""),
        ]

    monkeypatch.setattr(orchestration, "crawl_for_preview", fake_crawl)
    monkeypatch.setattr(orchestration, "_resolve_search_provider", lambda session: None)

    report = _make_report(session)
    router = ModelRouter(providers={})  # forces every AI-dependent stage to degrade
    settings = Settings()

    result = asyncio.run(
        orchestration.generate_preview_report(session=session, report=report, router=router, settings=settings)
    )

    assert result.status == "ready"
    assert result.error_message is None
    blob = result.report
    assert blob["status"] == "ready"
    assert blob["store"]["brand_name"] == "زهور"
    assert blob["store"]["domain"] == "zuhoor.sa"
    assert len(blob["queries"]) > 0
    assert blob["recommendation"]["title"]
    # every search leg failed -> no successful sample -> honest "limited" estimate, never a guessed score
    assert blob["visibility"] == {"mode": "estimated", "score": None, "level": "limited"}
    assert blob["competitors"] == []
    assert "topic" in blob["recommendation"]
    assert "evidence" in blob["recommendation"]


def test_report_reaches_ready_honestly_when_store_has_no_readable_product_names(session, monkeypatch):
    """Real-world case found live against taqitex.com: a storefront whose
    product JSON-LD 'name' is a bare SKU code ('#23', '#32', ...) and whose
    crawl never reaches a real category page. Locks down the full,
    end-to-end contract the frontend actually reads (the same report blob
    GET /preview-reports/{id} returns) for this exact degraded-data case:
    no numeric-code clutter in products, an honest empty query set (never
    a stale/mismatched count), and a recommendation that reads as ordinary
    advice — never a "the system didn't find enough data" admission."""
    async def fake_crawl(store_url, settings):
        home = PageFacts(url=f"{store_url}/", title="مؤسسة تقي للأقمشة")
        products = [
            CrawledPage(
                facts=PageFacts(url=f"{store_url}/{n}/p{n}", title=f"#{n}"),
                page_type="product",
                product={"name": f"#{n}"},
                html="",
            )
            for n in range(1, 6)
        ]
        return [CrawledPage(facts=home, page_type="home", product=None, html=""), *products]

    monkeypatch.setattr(orchestration, "crawl_for_preview", fake_crawl)
    monkeypatch.setattr(orchestration, "_resolve_search_provider", lambda session: None)

    report = _make_report(session, store_url="https://taqitex.example")
    router = ModelRouter(providers={})
    settings = Settings()

    result = asyncio.run(
        orchestration.generate_preview_report(session=session, report=report, router=router, settings=settings)
    )

    assert result.status == "ready"
    blob = result.report
    assert blob["store"]["products"] == []
    assert blob["store"]["categories"] == []
    assert blob["queries"] == []
    assert blob["visibility"] == {"mode": "estimated", "score": None, "level": "limited"}
    assert blob["competitors"] == []
    recommendation = blob["recommendation"]
    assert recommendation["title"]
    assert recommendation["reason"]
    assert recommendation["action"]
    for banned in ("لم نجد بيانات كافية", "بيانات غير كافية", "حدث خطأ"):
        assert banned not in recommendation["reason"]
        assert banned not in recommendation["title"]


def test_report_fails_cleanly_when_crawl_raises(session, monkeypatch):
    async def failing_crawl(store_url, settings):
        raise RuntimeError("dns resolution failed")

    monkeypatch.setattr(orchestration, "crawl_for_preview", failing_crawl)

    report = _make_report(session)
    router = ModelRouter(providers={})
    settings = Settings()

    result = asyncio.run(
        orchestration.generate_preview_report(session=session, report=report, router=router, settings=settings)
    )

    assert result.status == "failed"
    assert "dns resolution failed" in result.error_message
    assert result.report is None
