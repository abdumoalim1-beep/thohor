"""Stage 4 — template-based query generation is pure and AI-free, so these
are plain function tests: no dedup, capped at 30, generic subjects
rejected, never pads with weak queries when data is thin."""

from app.preview_reports.queries import TARGET_QUERY_COUNT, generate_search_queries


def test_generates_up_to_target_count_with_no_duplicates():
    facts = {
        "category_names": ["أثاث مكتبي", "كراسي مكتب", "طاولات اجتماعات"],
        "product_names": ["كرسي مكتب دوار", "طاولة اجتماعات", "كرسي مدير جلد", "رف كتب خشبي", "خزانة ملفات"],
    }
    queries = generate_search_queries(facts)
    assert len(queries) == TARGET_QUERY_COUNT
    assert len({q["query"] for q in queries}) == len(queries)


def test_never_pads_with_weak_queries_when_data_is_thin():
    facts = {"category_names": ["أحذية"], "product_names": ["حذاء رياضي"]}
    queries = generate_search_queries(facts)
    # 4 category templates + 5 product templates, one subject each = at most 9
    assert 0 < len(queries) <= 9
    assert len({q["query"] for q in queries}) == len(queries)


def test_rejects_generic_or_incomprehensible_subjects():
    facts = {"category_names": ["غير مصنف", "متجر", "x"], "product_names": ["كل المنتجات", "123"]}
    queries = generate_search_queries(facts)
    assert queries == []


def test_empty_facts_produce_no_queries():
    assert generate_search_queries({"category_names": [], "product_names": []}) == []


def test_every_query_is_grounded_in_a_real_extracted_subject():
    facts = {"category_names": ["عطور نسائية"], "product_names": []}
    queries = generate_search_queries(facts)
    assert queries
    for q in queries:
        assert q["subject"] == "عطور نسائية"
        assert "عطور نسائية" in q["query"]


def test_fallback_category_used_only_when_no_deterministic_category_found():
    facts = {"category_names": [], "product_names": []}
    queries = generate_search_queries(facts, fallback_category="أقمشة")
    assert queries
    assert all(q["subject"] == "أقمشة" for q in queries)
    # deterministic categories, when present, are never overridden by the fallback
    facts_with_category = {"category_names": ["عطور نسائية"], "product_names": []}
    queries2 = generate_search_queries(facts_with_category, fallback_category="أقمشة")
    assert all(q["subject"] == "عطور نسائية" for q in queries2)


def test_invalid_fallback_category_produces_no_queries():
    facts = {"category_names": [], "product_names": []}
    assert generate_search_queries(facts, fallback_category="") == []
    assert generate_search_queries(facts, fallback_category="غير مصنف") == []
