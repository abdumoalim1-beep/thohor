"""Stage 6+7 — deterministic brand detection and the visibility formula.
Covers the spec's core safety rule: a failed search must never become a
false "not found", and the denominator is always successful searches
only, never total attempted."""

from app.preview_reports.visibility import (
    analyze_ai_result,
    analyze_google_result,
    classify_visibility,
    compute_visibility_scores,
    enrich_query_results,
    normalize_brand_text,
)


def test_normalize_brand_text_unifies_diacritics_alef_and_ta_marbuta():
    assert normalize_brand_text("ظُهُور") == normalize_brand_text("ظهور")
    assert normalize_brand_text("أحمد") == normalize_brand_text("احمد")
    assert normalize_brand_text("مدرسة") == normalize_brand_text("مدرسه")


def test_google_result_found_at_correct_position():
    google = {
        "status": "success",
        "results": [
            {"rank": 1, "domain": "other.com", "url": "https://other.com", "title": "t"},
            {"rank": 2, "domain": "zuhoor.sa", "url": "https://zuhoor.sa/x", "title": "t"},
        ],
    }
    result = analyze_google_result(google, store_domain="zuhoor.sa")
    assert result["brand_found"] is True
    assert result["position"] == 2


def test_google_result_not_found_is_false_not_unknown():
    google = {"status": "success", "results": [{"rank": 1, "domain": "other.com", "url": "https://other.com"}]}
    result = analyze_google_result(google, store_domain="zuhoor.sa")
    assert result["brand_found"] is False
    assert result["position"] is None


def test_failed_google_search_never_becomes_a_false_negative():
    result = analyze_google_result({"status": "failed"}, store_domain="zuhoor.sa")
    assert result["status"] == "failed"
    assert result["brand_found"] is None
    assert result["position"] is None


def test_ai_result_found_via_text_mention():
    ai = {"status": "success", "raw_result": "أنصحك بمتجر زهور الجميل", "sources": []}
    result = analyze_ai_result(ai, brand_candidates=["زهور"], store_domain="zuhoor.sa")
    assert result["brand_found"] is True


def test_ai_result_found_via_citation_domain():
    ai = {"status": "success", "raw_result": "لا يوجد اقتراح واضح", "sources": [{"url": "https://zuhoor.sa/p"}]}
    result = analyze_ai_result(ai, brand_candidates=["غير ذلك"], store_domain="zuhoor.sa")
    assert result["brand_found"] is True
    assert result["position"] == 1


def test_ai_result_empty_answer_is_unknown_not_false():
    ai = {"status": "success", "raw_result": "", "sources": []}
    result = analyze_ai_result(ai, brand_candidates=["زهور"], store_domain="zuhoor.sa")
    assert result["brand_found"] is None


def test_failed_ai_search_never_becomes_a_false_negative():
    result = analyze_ai_result({"status": "failed"}, brand_candidates=["زهور"], store_domain="zuhoor.sa")
    assert result["brand_found"] is None


def test_visibility_score_excludes_failed_searches_from_denominator():
    enriched = [
        {"query": "q1", "google": {"status": "success", "brand_found": True}, "ai": {"status": "success", "brand_found": False}},
        {"query": "q2", "google": {"status": "success", "brand_found": False}, "ai": {"status": "failed", "brand_found": None}},
        {"query": "q3", "google": {"status": "failed", "brand_found": None}, "ai": {"status": "success", "brand_found": False}},
    ]
    scores = compute_visibility_scores(enriched)
    # google: 2 successful (q1,q2), 1 appeared -> 50%
    assert scores["google"] == 50
    # ai: 2 successful (q1,q3), 0 appeared -> 0%
    assert scores["ai"] == 0
    # overall is query-level: all 3 queries have >=1 successful leg, only
    # q1 appeared on either leg -> 1/3 -> 33%
    assert scores["overall"] == 33
    assert scores["overall_details"] == {"appeared": 1, "successful": 3}
    assert scores["details"]["google"]["successful_searches"] == 2
    assert scores["details"]["ai"]["successful_searches"] == 2


def test_visibility_score_is_none_when_everything_failed():
    enriched = [{"query": "q1", "google": {"status": "failed"}, "ai": {"status": "failed"}}]
    scores = compute_visibility_scores(enriched)
    assert scores["overall"] is None
    assert scores["google"] is None
    assert scores["ai"] is None
    assert scores["overall_details"] == {"appeared": 0, "successful": 0}


def _enriched(n_success_appeared=0, n_success_missing=0, n_failed=0):
    queries = []
    for i in range(n_success_appeared):
        queries.append({"query": f"hit{i}", "google": {"status": "success", "brand_found": True}, "ai": {"status": "failed", "brand_found": None}})
    for i in range(n_success_missing):
        queries.append({"query": f"miss{i}", "google": {"status": "success", "brand_found": False}, "ai": {"status": "failed", "brand_found": None}})
    for i in range(n_failed):
        queries.append({"query": f"fail{i}", "google": {"status": "failed", "brand_found": None}, "ai": {"status": "failed", "brand_found": None}})
    return queries


def test_classify_visibility_is_measured_above_the_sample_threshold():
    enriched = _enriched(n_success_appeared=8, n_success_missing=4)  # 12 successful queries
    scores = compute_visibility_scores(enriched)
    result = classify_visibility(scores, enriched, competitors=[])
    assert result["mode"] == "measured"
    assert result["score"] == scores["overall"]
    assert result["successful_checks"] == 12
    assert result["brand_mentions"] == 8


def test_classify_visibility_is_limited_when_nothing_succeeded():
    enriched = _enriched(n_failed=5)
    scores = compute_visibility_scores(enriched)
    result = classify_visibility(scores, enriched, competitors=[])
    assert result == {"mode": "estimated", "score": None, "level": "limited"}


def test_classify_visibility_estimates_under_50_only_with_real_weak_signal():
    # 3 successful queries, all confirmed non-appearances -> below threshold
    # but there IS real evidence of weakness, so under_50 is justified.
    enriched = _enriched(n_success_missing=3)
    scores = compute_visibility_scores(enriched)
    competitors = [{"domain": "other.com", "appearances": 2}]
    result = classify_visibility(scores, enriched, competitors=competitors)
    assert result["mode"] == "estimated"
    assert result["score"] is None
    assert result["level"] == "low"
    assert result["display_range"] == "under_50"
    assert "limited_brand_presence" in result["reasons"]
    assert "competitor_presence" in result["reasons"]
    assert "content_gap" in result["reasons"]


def test_classify_visibility_never_certifies_strong_visibility_from_thin_sample():
    # only 3 successful queries, ALL appeared -> too thin to trust, and no
    # weakness evidence exists, so must stay 'limited' rather than implying
    # a strong/positive visibility from 3 samples.
    enriched = _enriched(n_success_appeared=3)
    scores = compute_visibility_scores(enriched)
    result = classify_visibility(scores, enriched, competitors=[])
    assert result == {"mode": "estimated", "score": None, "level": "limited"}


def test_enrich_query_results_preserves_query_metadata():
    queries = [{
        "query": "أفضل عطور", "subject": "عطور", "subject_type": "category",
        "google": {"status": "success", "results": []}, "ai": {"status": "failed"},
    }]
    enriched = enrich_query_results(queries, brand_name="زهور", domain="zuhoor.sa")
    assert enriched[0]["subject"] == "عطور"
    assert enriched[0]["google"]["brand_found"] is False
    assert enriched[0]["ai"]["brand_found"] is None
