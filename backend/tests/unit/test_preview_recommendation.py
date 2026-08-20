"""Stage 11 — the single recommendation. Covers evidence-building (only
genuinely-confirmed non-appearances count, never unknown/failed), the
no-provider-configured fallback path (must never raise, must never sink
the report), and that a recommendation is always grounded in real missing
queries rather than a generic platitude when evidence exists."""

import asyncio

from sqlmodel import Session, SQLModel, create_engine

from app.preview_reports.recommendation import (
    build_missing_query_evidence,
    build_recommendation,
)
from app.providers.ai.router import ModelRouter


def test_missing_query_evidence_excludes_unknown_and_failed():
    enriched = [
        {"query": "q1", "subject": "عطور", "google": {"status": "success", "brand_found": False}, "ai": {"status": "success", "brand_found": True}},
        {"query": "q2", "subject": "عطور", "google": {"status": "failed"}, "ai": {"status": "success", "brand_found": None}},
        {"query": "q3", "subject": "عطور", "google": {"status": "success", "brand_found": True}, "ai": {"status": "success", "brand_found": True}},
    ]
    missing = build_missing_query_evidence(enriched)
    assert len(missing) == 1
    assert missing[0]["query"] == "q1"
    assert missing[0]["missing_in"] == ["google"]


def test_fallback_recommendation_used_when_no_provider_configured():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    enriched = [
        {"query": "أفضل عطور نسائية", "subject": "عطور نسائية", "google": {"status": "success", "brand_found": False}, "ai": {"status": "success", "brand_found": False}},
        {"query": "وين ألقى عطور نسائية", "subject": "عطور نسائية", "google": {"status": "success", "brand_found": False}, "ai": {"status": "failed"}},
    ]
    with Session(engine) as session:
        router = ModelRouter(providers={})
        result = asyncio.run(build_recommendation(
            session=session, router=router,
            understanding={"brand_name": "زهور", "category": "عطور"},
            enriched_queries=enriched,
        ))
    assert result["title"]
    assert "عطور نسائية" in result["reason"]
    assert result["action"]
    assert result["topic"] == "عطور نسائية"
    assert result["evidence"] == ["أفضل عطور نسائية", "وين ألقى عطور نسائية"]


def test_fallback_recommendation_with_no_missing_queries_uses_known_category():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    enriched = [{"query": "q1", "subject": "عطور", "google": {"status": "success", "brand_found": True}, "ai": {"status": "success", "brand_found": True}}]
    with Session(engine) as session:
        router = ModelRouter(providers={})
        result = asyncio.run(build_recommendation(
            session=session, router=router,
            understanding={"brand_name": "زهور", "category": "عطور"},
            enriched_queries=enriched,
        ))
    assert result["title"]
    assert result["reason"]
    assert result["action"]
    assert result["topic"] == "عطور"
    assert result["evidence"] == []
    assert "لم نجد بيانات كافية" not in result["reason"]


def test_tied_subjects_break_toward_the_word_that_recurs_across_categories_not_crawl_order():
    """Real case observed live on kayanabaya.com ("متجر كيان لأرقي العبايات"):
    every crawled category was equally missing, and the pick used to just
    be whichever came first in the raw crawl order — landing on a minor
    accessory sub-category ("عطر ومنديل عبايات") instead of the store's
    actual core product. "أحدث العبايات" is listed AFTER the perfume
    subject here on purpose, so a pass is only possible via the
    centrality tie-break (عبايات recurs in both subjects, so it wins on
    being the shorter of the two), not crawl order."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    enriched = [
        {"query": "أفضل عطر ومنديل عبايات", "subject": "عطر ومنديل عبايات", "google": {"status": "success", "brand_found": False}, "ai": {"status": "success", "brand_found": False}},
        {"query": "أفضل متجر عطر ومنديل عبايات", "subject": "عطر ومنديل عبايات", "google": {"status": "success", "brand_found": False}, "ai": {"status": "success", "brand_found": False}},
        {"query": "أفضل أحدث العبايات", "subject": "أحدث العبايات", "google": {"status": "success", "brand_found": False}, "ai": {"status": "success", "brand_found": False}},
        {"query": "أفضل متجر أحدث العبايات", "subject": "أحدث العبايات", "google": {"status": "success", "brand_found": False}, "ai": {"status": "success", "brand_found": False}},
    ]
    with Session(engine) as session:
        router = ModelRouter(providers={})
        result = asyncio.run(build_recommendation(
            session=session, router=router,
            understanding={"brand_name": "متجر كيان لأرقي العبايات", "category": "أزياء نسائية"},
            enriched_queries=enriched,
        ))
    assert result["topic"] == "أحدث العبايات"
    # evidence must actually be about the chosen topic, not whichever
    # subject happened to appear first in the missing-queries list
    assert result["evidence"] == ["أفضل أحدث العبايات", "أفضل متجر أحدث العبايات"]


def test_tied_subjects_do_not_false_positive_on_a_sub_brand_sharing_the_store_name():
    """The first version of this tie-break matched against brand_name text
    directly, which broke on exactly this real shape from the same real
    store: a sub-brand collection named "كيان بريميوم" trivially shares
    the word "كيان" with the brand name "متجر كيان لأرقي العبايات" without
    being a real product type at all. Word-recurrence across the store's
    OWN categories doesn't have that false positive — "عبايات" recurs
    across 3 subjects here (real product signal), "كيان"/"بريميوم" each
    appear exactly once."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def _pair(subject: str) -> list[dict]:
        return [
            {"query": f"أفضل {subject}", "subject": subject, "google": {"status": "success", "brand_found": False}, "ai": {"status": "success", "brand_found": False}},
            {"query": f"أفضل متجر {subject}", "subject": subject, "google": {"status": "success", "brand_found": False}, "ai": {"status": "success", "brand_found": False}},
        ]

    enriched = _pair("كيان بريميوم") + _pair("أحدث العبايات") + _pair("كل العبايات")
    with Session(engine) as session:
        router = ModelRouter(providers={})
        result = asyncio.run(build_recommendation(
            session=session, router=router,
            understanding={"brand_name": "متجر كيان لأرقي العبايات", "category": "أزياء نسائية"},
            enriched_queries=enriched,
        ))
    assert result["topic"] != "كيان بريميوم"
    assert result["topic"] in ("أحدث العبايات", "كل العبايات")


def test_fallback_recommendation_with_nothing_at_all_is_still_graceful_never_admits_failure():
    """Zero missing-query evidence AND no resolved category (e.g. a store
    whose product names were all unusable, like bare SKU codes) — the
    absolute floor case. Must still read as ordinary advice, never as a
    'the system didn't find enough data' admission."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        router = ModelRouter(providers={})
        result = asyncio.run(build_recommendation(
            session=session, router=router,
            understanding={"brand_name": "متجري", "category": ""},
            enriched_queries=[],
        ))
    assert result["title"]
    assert result["reason"]
    assert result["action"]
    assert result["topic"] is None
    assert result["evidence"] == []
    for banned in ("لم نجد بيانات كافية", "بيانات غير كافية", "حدث خطأ"):
        assert banned not in result["reason"]
        assert banned not in result["title"]
