"""Stage 8 — competitors are extracted from the same 30 query results, no
separate discovery pipeline. Covers: the store's own domain is never
listed as its own competitor, known non-competitor domains (marketplaces,
social, video, etc.) are excluded via the existing curated registry, and
frequency/visibility aggregate correctly across both Google and AI
citation sources."""

from app.preview_reports.competitors import extract_competitors
from app.preview_reports.visibility import enrich_query_results


def test_excludes_own_domain_and_known_marketplaces():
    queries = [{
        "query": "q1",
        "google": {"status": "success", "results": [
            {"rank": 1, "domain": "zuhoor.sa", "url": "https://zuhoor.sa", "title": "t"},
            {"rank": 2, "domain": "amazon.sa", "url": "https://amazon.sa", "title": "t"},
            {"rank": 3, "domain": "rival.com", "url": "https://rival.com", "title": "t"},
        ]},
        "ai": {"status": "failed"},
    }]
    enriched = enrich_query_results(queries, brand_name="زهور", domain="zuhoor.sa")
    competitors = extract_competitors(enriched, store_domain="zuhoor.sa")
    domains = [c["domain"] for c in competitors]
    assert "zuhoor.sa" not in domains
    assert "amazon.sa" not in domains
    assert "rival.com" in domains


def test_aggregates_appearances_across_google_and_ai_sources():
    queries = [
        {
            "query": "q1",
            "google": {"status": "success", "results": [{"rank": 1, "domain": "rival.com", "url": "https://rival.com", "title": "t"}]},
            "ai": {"status": "failed"},
        },
        {
            "query": "q2",
            "google": {"status": "failed"},
            "ai": {"status": "success", "raw_result": "no mention", "sources": [{"url": "https://rival.com/x"}]},
        },
    ]
    enriched = enrich_query_results(queries, brand_name="زهور", domain="zuhoor.sa")
    competitors = extract_competitors(enriched, store_domain="zuhoor.sa")
    assert len(competitors) == 1
    assert competitors[0]["domain"] == "rival.com"
    assert competitors[0]["appearances"] == 2


def test_no_competitors_found_returns_empty_list_never_fabricated():
    queries = [{"query": "q1", "google": {"status": "failed"}, "ai": {"status": "failed"}}]
    enriched = enrich_query_results(queries, brand_name="زهور", domain="zuhoor.sa")
    assert extract_competitors(enriched, store_domain="zuhoor.sa") == []


def test_caps_at_max_competitors_sorted_by_appearances():
    results = [
        {"rank": i + 1, "domain": f"rival{i}.com", "url": f"https://rival{i}.com", "title": "t"} for i in range(15)
    ]
    queries = [{"query": "q1", "google": {"status": "success", "results": results}, "ai": {"status": "failed"}}]
    enriched = enrich_query_results(queries, brand_name="زهور", domain="zuhoor.sa")
    competitors = extract_competitors(enriched, store_domain="zuhoor.sa")
    assert len(competitors) == 10
