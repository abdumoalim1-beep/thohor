"""Stage 3 — deterministic facts extraction (no network, no AI) plus the
one optional LLM normalization call, which must degrade to the
deterministic facts alone on any failure rather than sinking the report.
Also confirms the PreviewReport name-resolution chain never starts with
web search (unlike the /signup identity resolver) — JSON-LD/og/title/
logo/domain only."""

import asyncio

from sqlmodel import Session, SQLModel, create_engine

from app.crawler.crawl import CrawledPage
from app.crawler.extract import PageFacts
from app.preview_reports.understanding import build_understanding, extract_deterministic_facts
from app.providers.ai.router import ModelRouter


def _home_page(**overrides) -> CrawledPage:
    facts = PageFacts(url="https://zuhoor.sa/", title="متجر زهور | تسوق عطور", og_site_name="زهور")
    for key, value in overrides.items():
        setattr(facts, key, value)
    return CrawledPage(facts=facts, page_type="home", product=None, html="<html></html>")


def _product_page(name: str) -> CrawledPage:
    facts = PageFacts(url=f"https://zuhoor.sa/products/{name}", title=name)
    return CrawledPage(facts=facts, page_type="product", product={"name": name}, html="<html></html>")


def _category_page(name: str) -> CrawledPage:
    facts = PageFacts(url=f"https://zuhoor.sa/categories/{name}", h1=name)
    return CrawledPage(facts=facts, page_type="category", product=None, html="<html></html>")


def test_extract_deterministic_facts_resolves_name_without_web_search():
    pages = [_home_page(), _product_page("عطر ورد"), _category_page("عطور نسائية")]
    facts = extract_deterministic_facts(pages, "https://zuhoor.sa")
    assert facts["brand_name"] == "زهور"
    assert facts["brand_name_source"] == "og_site_name"
    assert facts["domain"] == "zuhoor.sa"
    assert "عطر ورد" in facts["product_names"]
    assert "عطور نسائية" in facts["category_names"]


def test_extract_deterministic_facts_falls_back_to_domain_when_nothing_else_exists():
    empty_home = CrawledPage(facts=PageFacts(url="https://mystore.sa/"), page_type="home", product=None, html="")
    facts = extract_deterministic_facts([empty_home], "https://mystore.sa")
    assert facts["brand_name"]
    assert facts["brand_name_source"] == "domain_guess"


def test_extract_deterministic_facts_handles_no_pages_at_all():
    facts = extract_deterministic_facts([], "https://mystore.sa")
    assert facts["brand_name"]
    assert facts["product_names"] == []
    assert facts["category_names"] == []


def test_extract_deterministic_facts_rejects_numeric_only_names():
    """Some storefronts (observed on Salla) put a bare SKU/variant code
    like '#23' in the product JSON-LD 'name' field instead of a real
    label — that's not a product name worth showing the merchant or
    handing to query generation, and must never surface in
    report.store.products as meaningless clutter."""
    pages = [
        _home_page(),
        _product_page("#23"),
        _product_page("#32"),
        _product_page("عطر ورد حقيقي"),
        _category_page("١٢٣"),
    ]
    facts = extract_deterministic_facts(pages, "https://zuhoor.sa")
    assert facts["product_names"] == ["عطر ورد حقيقي"]
    assert facts["category_names"] == []


def test_build_understanding_falls_back_when_no_provider_configured():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    facts = {
        "brand_name": "زهور", "title": "متجر زهور", "meta_description": "أفضل متجر عطور",
        "h1": None, "category_names": ["عطور نسائية"], "product_names": ["عطر ورد", "عطر ياسمين"],
    }
    with Session(engine) as session:
        router = ModelRouter(providers={})
        result = asyncio.run(build_understanding(session=session, router=router, facts=facts))
    assert result["brand_name"] == "زهور"
    assert result["category"] == "عطور نسائية"
    assert result["products"] == ["عطر ورد", "عطر ياسمين"]
    assert result["is_online_store"] is True


def test_build_understanding_fallback_says_not_a_store_when_no_products_were_crawled():
    """No LLM judgment available in the fallback path — must under-claim
    (false) rather than assume every analyzed site sells products."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    facts = {
        "brand_name": "شركة الحلول", "title": "شركة الحلول للاستشارات", "meta_description": "",
        "h1": None, "category_names": [], "product_names": [],
    }
    with Session(engine) as session:
        router = ModelRouter(providers={})
        result = asyncio.run(build_understanding(session=session, router=router, facts=facts))
    assert result["is_online_store"] is False
