"""Stage 11 — the single recommendation. Covers evidence-building (only
genuinely-confirmed non-appearances count, never unknown/failed), the
no-provider-configured fallback path (must never raise, must never sink
the report), and that a recommendation is always grounded in real missing
queries rather than a generic platitude when evidence exists."""

import asyncio

from sqlmodel import Session, SQLModel, create_engine

from app.preview_reports.recommendation import build_missing_query_evidence, build_recommendation
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
