"""Part Q3 — deterministic recommendation quality gate. Pure function over
plain (never-persisted) Recommendation objects — no DB needed."""

import uuid

from app.models.recommendation import Recommendation, RecommendationStatus
from app.opportunities.quality_gate import check_recommendation_batch_quality


def _make_rec(**overrides) -> Recommendation:
    defaults = dict(
        id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        opportunity_id=uuid.uuid4(),
        first_seen_research_run_id=uuid.uuid4(),
        last_seen_research_run_id=uuid.uuid4(),
        title="حسّن ظهورك في Google لـ 'قهوة مختصة'",
        what_to_do="راجع العنوان والوصف للصفحة الأقرب لهذه النية.",
        why_it_matters="المتجر غير ظاهر ضمن أفضل 10 نتيجة.",
        evidence_ids=["ev-1"],
        implementation_steps=["راجع العنوان", "حسّن المحتوى"],
        status=RecommendationStatus.new,
    )
    defaults.update(overrides)
    return Recommendation(**defaults)


def test_clean_batch_has_no_issues():
    batch = [
        _make_rec(title="حسّن ظهورك في Google لـ 'قهوة مختصة'"),
        _make_rec(title="اجعل متجرك يُذكر في إجابات AI عن 'مطحنة يدوية'"),
    ]

    issues = check_recommendation_batch_quality(batch)

    assert issues == []


def test_flags_raw_scraped_page_title_in_title():
    rec = _make_rec(
        title="منافيخ هواء كهربائية | بلاور تنظيف الغبار | بوش، هيونداي وسكيل | إكسترا السعودية",
    )

    issues = check_recommendation_batch_quality([rec])

    assert any(i.check == "raw_page_title" for i in issues)


def test_flags_raw_scraped_page_title_in_what_to_do():
    rec = _make_rec(what_to_do="منتج أ، منتج ب، منتج ج، منتج د | تصنيف عام")

    issues = check_recommendation_batch_quality([rec])

    assert any(i.check == "raw_page_title" for i in issues)


def test_flags_unsupported_claim_when_no_evidence():
    rec = _make_rec(evidence_ids=[])

    issues = check_recommendation_batch_quality([rec])

    assert any(i.check == "unsupported_claim" for i in issues)


def test_flags_recommendation_supported_by_only_one_signal():
    rec = _make_rec(evidence_ids=[uuid.uuid4()])

    issues = check_recommendation_batch_quality([rec])

    assert any(i.check == "unsupported_claim" for i in issues)


def test_flags_generic_fallback_advice():
    rec = _make_rec(implementation_steps=["راجع تفاصيل هذه الفرصة واتخذ إجراءً مناسبًا"])

    issues = check_recommendation_batch_quality([rec])

    assert any(i.check == "generic_advice" for i in issues)


def test_flags_near_duplicate_titles_in_the_same_batch():
    batch = [
        _make_rec(title="حسّن ظهورك في Google لـ قهوة مختصة"),
        _make_rec(title="حسّن ظهورك في Google لـ قهوة مختصة الآن"),
    ]

    issues = check_recommendation_batch_quality(batch)

    assert any(i.check == "duplicate_recommendation" for i in issues)


def test_does_not_flag_genuinely_different_titles_as_duplicates():
    batch = [
        _make_rec(title="حسّن ظهورك في Google لـ قهوة مختصة"),
        _make_rec(title="اجعل متجرك يُذكر في إجابات AI عن مطحنة يدوية"),
    ]

    issues = check_recommendation_batch_quality(batch)

    assert not any(i.check == "duplicate_recommendation" for i in issues)


def test_empty_batch_has_no_issues():
    assert check_recommendation_batch_quality([]) == []
