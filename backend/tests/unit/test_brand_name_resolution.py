"""Extended display-name fallback chain (app.store_intelligence.
brand_name_resolution) — engaged only once a real crawl-extracted
Brand.name and web-search identity resolution are both exhausted. Covers
every tier in isolation, in priority order, plus the domain-guess last
resort that must never fail."""

from app.store_intelligence.brand_name_resolution import (
    _find_logo_alt_text,
    resolve_best_available_name,
)


def test_organization_json_ld_wins_over_everything_below_it():
    extraction = {
        "json_ld": [{"@type": "Organization", "name": "فلاوري الرسمي"}],
        "og_site_name": "اسم مختلف من og",
        "title": "عنوان الصفحة | متجر",
        "images": [{"url": "https://x.com/logo.png", "alt": "شعار آخر"}],
    }
    name, source = resolve_best_available_name(home_extraction=extraction, base_url="https://flowery.example")
    assert name == "فلاوري الرسمي"
    assert source == "structured_data"


def test_website_json_ld_also_counts_as_structured_data():
    extraction = {"json_ld": [{"@type": "WebSite", "name": "متجر الورد"}]}
    name, source = resolve_best_available_name(home_extraction=extraction, base_url="https://flowery.example")
    assert name == "متجر الورد"
    assert source == "structured_data"


def test_json_ld_graph_wrapped_website_is_unwrapped():
    extraction = {"json_ld": [{"@graph": [{"@type": "WebSite", "name": "متجر داخل @graph"}]}]}
    name, source = resolve_best_available_name(home_extraction=extraction, base_url="https://flowery.example")
    assert name == "متجر داخل @graph"
    assert source == "structured_data"


def test_og_site_name_used_when_no_structured_data():
    extraction = {"json_ld": [], "og_site_name": "اسم من og:site_name", "title": "عنوان مختلف"}
    name, source = resolve_best_available_name(home_extraction=extraction, base_url="https://flowery.example")
    assert name == "اسم من og:site_name"
    assert source == "og_site_name"


def test_page_title_used_when_no_structured_data_or_og():
    extraction = {"title": "فلاوري | أفضل متجر ورد في الرياض"}
    name, source = resolve_best_available_name(home_extraction=extraction, base_url="https://flowery.example")
    assert name == "فلاوري"
    assert source == "page_title"


def test_page_title_cleanup_handles_em_dash_separator_too():
    extraction = {"title": "فلاوري — الصفحة الرئيسية"}
    name, source = resolve_best_available_name(home_extraction=extraction, base_url="https://flowery.example")
    assert name == "فلاوري"
    assert source == "page_title"


def test_logo_alt_text_used_when_no_structured_data_og_or_title():
    extraction = {
        "images": [
            {"url": "https://x.com/banner.jpg", "alt": "بانر ترويجي"},
            {"url": "https://x.com/site-logo.png", "alt": "فلاوري"},
        ]
    }
    name, source = resolve_best_available_name(home_extraction=extraction, base_url="https://flowery.example")
    assert name == "فلاوري"
    assert source == "logo_alt"


def test_find_logo_alt_text_matches_on_url_when_alt_is_empty():
    """An empty alt on the logo image itself isn't usable, but a later
    image with a real alt and a logo-marked URL should still be picked."""
    images = [
        {"url": "https://x.com/logo.png", "alt": ""},
        {"url": "https://x.com/site-logo-alt.png", "alt": "اسم من رابط الشعار"},
    ]
    assert _find_logo_alt_text(images) == "اسم من رابط الشعار"


def test_domain_derived_name_is_the_final_resort_and_never_fails():
    """The one tier the user explicitly said must still be usable — 'even
    if domain-derived' — start-visibility-analysis-automatically depends
    on this tier never returning nothing."""
    name, source = resolve_best_available_name(home_extraction={}, base_url="https://modernsupply.com.sa/")
    assert name == "Modernsupply"
    assert source == "domain_guess"


def test_real_bug_scenario_web_search_failed_but_crawl_had_structured_data():
    """The exact live-caught scenario: identity_run.findings.skipped=True
    (web_search_unavailable_or_failed) but the home page's own JSON-LD
    still names the store — this must resolve confidently, never block."""
    extraction = {"json_ld": [{"@type": "Organization", "name": "مودرن سبلاي"}]}
    name, source = resolve_best_available_name(home_extraction=extraction, base_url="https://modernsupply.com.sa/")
    assert name == "مودرن سبلاي"
    assert source == "structured_data"
