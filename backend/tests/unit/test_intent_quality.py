from sqlmodel import select

from app.intent.quality import (
    INTENT_QUALITY_THRESHOLD,
    apply_quality_gate,
    classify_intent_type,
    score_intent_quality,
)
from app.models.catalog import Brand, Category
from app.models.intent import Intent, IntentSource
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-intent-quality")
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


def test_score_intent_quality_rejects_scraped_page_title():
    """Exactly the G-A failure mode on extra.com."""
    result = score_intent_quality(
        topic="منافيخ هواء كهربائية | بلاور تنظيف الغبار وأوراق الشجر | بوش، هيونداي وسكيل | إكسترا السعودية",
        category=None, commercial_stage=None, source=IntentSource.ai_expansion,
        catalog_tokens=set(), brand_tokens=set(),
    )
    assert result.is_accepted is False
    assert result.score < INTENT_QUALITY_THRESHOLD
    assert "scraped" in result.reason


def test_score_intent_quality_rejects_short_scraped_title_with_no_other_penalty():
    """Part Q3 regression: a *short* (<=9 word) pipe-separated title used
    to only lose the 0.5 scraped-title penalty and land exactly at
    INTENT_QUALITY_THRESHOLD (0.5) with no other violation stacked on top
    — landing on the boundary meant `score >= INTENT_QUALITY_THRESHOLD`
    was true and it got ACCEPTED. Caught via a real books.toscrape.com
    replay run where 'Academic | Books to Scrape - Sandbox' (7 words)
    reached a customer-facing recommendation. Must always be a hard
    reject, regardless of length or any other check."""
    result = score_intent_quality(
        topic="Academic | Books to Scrape - Sandbox",
        category=None, commercial_stage=None, source=IntentSource.deterministic_catalog,
        catalog_tokens=set(), brand_tokens=set(),
    )
    assert result.is_accepted is False
    assert result.score == 0.0
    assert "scraped" in result.reason


def test_score_intent_quality_rejects_policy_page():
    """Part R2-F2 — policy pages get their own type (distinct from site
    chrome like 'الرئيسية'/'سلة التسوق'), so the rejection reason is
    precise and machine-parseable ('policy_page: ...'), not a generic
    'navigation' label."""
    result = score_intent_quality(
        topic="سياسة الخصوصية", category=None, commercial_stage=None, source=IntentSource.ai_expansion,
        catalog_tokens=set(), brand_tokens=set(),
    )
    assert result.is_accepted is False
    assert result.intent_type == "policy"
    assert "policy_page" in result.reason


def test_score_intent_quality_rejects_navigational_site_chrome():
    result = score_intent_quality(
        topic="سلة التسوق", category=None, commercial_stage=None, source=IntentSource.ai_expansion,
        catalog_tokens=set(), brand_tokens=set(),
    )
    assert result.is_accepted is False
    assert result.intent_type == "navigational"
    assert "site_navigation" in result.reason


def test_score_intent_quality_accepts_clean_catalog_derived_intent():
    result = score_intent_quality(
        topic="أدوات تحضير القهوة", category="أدوات القهوة", commercial_stage=None,
        source=IntentSource.deterministic_catalog, catalog_tokens={"أدوات", "تحضير", "القهوة"}, brand_tokens=set(),
    )
    assert result.is_accepted is True
    assert result.score == 1.0


def test_score_intent_quality_deterministic_catalog_source_never_penalized_for_catalog_overlap():
    # source=deterministic_catalog is exempt from the "must overlap catalog" check —
    # it IS the catalog by construction.
    result = score_intent_quality(
        topic="تصنيف غريب غير معروف", category=None, commercial_stage=None,
        source=IntentSource.deterministic_catalog, catalog_tokens=set(), brand_tokens=set(),
    )
    assert result.is_accepted is True


def test_score_intent_quality_penalizes_ai_expansion_topic_unrelated_to_catalog():
    # A single weak signal (no catalog overlap) lowers the score but isn't
    # enough on its own to reject — only combined/strong signals (scraped
    # title pattern, excessive length) push below threshold by themselves.
    result = score_intent_quality(
        topic="عطور نسائية فاخرة للمناسبات", category=None, commercial_stage=None, source=IntentSource.ai_expansion,
        catalog_tokens={"قهوة", "مطحنة", "فلتر"}, brand_tokens=set(),
    )
    assert result.score < 1.0
    assert "catalog" in result.reason


def test_classify_intent_type_detects_comparison_problem_local_informational():
    """Part R2-F2 — comparison/problem/local/informational all fold into
    one accepted, measurable type (informational_commercial): each still
    carries real commercial-discovery value ('أفضل X' is a comparison
    shopping query), unlike the excluded navigational/account/policy/
    generic types."""
    assert classify_intent_type("مقارنة بين X و Y", None, None) == "informational_commercial"
    assert classify_intent_type("كيف أحل مشكلة تسرب الماء", None, None) == "informational_commercial"
    assert classify_intent_type("أقرب فرع لي", None, None) == "informational_commercial"
    assert classify_intent_type("لماذا يهم نوع حبوب القهوة", None, None) == "informational_commercial"


def test_apply_quality_gate_persists_scores_and_filters_rejected_intents(session):
    store, run = _make_store_and_run(session)
    session.add(Category(store_id=store.id, name="أدوات القهوة"))
    session.commit()

    good = Intent(
        store_id=store.id, research_run_id=run.id, topic="أدوات تحضير القهوة", category="أدوات القهوة",
        country="sa", language="ar", source=IntentSource.deterministic_catalog,
    )
    scraped_title = Intent(
        store_id=store.id, research_run_id=run.id,
        topic="منافيخ هواء كهربائية | بلاور تنظيف الغبار وأوراق الشجر | بوش، هيونداي وسكيل | إكسترا السعودية",
        country="sa", language="ar", source=IntentSource.ai_expansion,
    )
    session.add(good)
    session.add(scraped_title)
    session.commit()
    session.refresh(good)
    session.refresh(scraped_title)

    accepted = apply_quality_gate(session, [good, scraped_title], store.id)

    assert [i.id for i in accepted] == [good.id]

    session.refresh(good)
    session.refresh(scraped_title)
    assert good.is_accepted is True
    assert good.quality_score == 1.0
    assert scraped_title.is_accepted is False
    assert scraped_title.quality_score < INTENT_QUALITY_THRESHOLD
    assert scraped_title.quality_reason is not None


def test_apply_quality_gate_rejects_near_duplicate_intents(session):
    store, run = _make_store_and_run(session)

    first = Intent(
        store_id=store.id, research_run_id=run.id, topic="أفضل قهوة مختصة", country="sa", language="ar",
        source=IntentSource.ai_expansion,
    )
    near_dup = Intent(
        store_id=store.id, research_run_id=run.id, topic="وش أفضل متجر قهوة مختصة", country="sa", language="ar",
        source=IntentSource.ai_expansion,
    )
    session.add(first)
    session.add(near_dup)
    session.commit()
    session.refresh(first)
    session.refresh(near_dup)

    accepted = apply_quality_gate(session, [first, near_dup], store.id)

    assert len(accepted) == 1
    session.refresh(first)
    session.refresh(near_dup)
    rejected = first if not first.is_accepted else near_dup
    assert "near-duplicate" in (rejected.quality_reason or "")


def test_apply_quality_gate_recognizes_brand_topic(session):
    store, run = _make_store_and_run(session)
    session.add(Brand(store_id=store.id, name="روستنج هاوس", aliases=["Roasting House"]))
    session.commit()

    intent = Intent(
        store_id=store.id, research_run_id=run.id, topic="متجر روستنج هاوس", country="sa", language="ar",
        source=IntentSource.ai_expansion,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    accepted = apply_quality_gate(session, [intent], store.id)

    assert len(accepted) == 1
    session.refresh(intent)
    assert intent.intent_type == "brand"


# --- Part R2-F2: the exact generic/navigational patterns Round 2 confirmed
# reaching acceptance across all 4 stores (alsaifgallery, jarir, chewy,
# glossier), each now caught by a pattern family rather than an exact-match
# blacklist entry that would only have covered this one phrasing. ---

_ROUND2_NON_DISCOVERY_TOPICS = [
    ("تسوق آمن", "generic"),  # alsaifgallery + chewy — "safe shopping"
    ("تسوق سهل", "generic"),  # alsaifgallery — "easy shopping"
    ("تسوق مريح", "generic"),  # alsaifgallery — "comfortable shopping"
    ("تسوق عبر الإنترنت", "generic"),  # alsaifgallery — "online shopping"
    ("حسابي في جرير", "account_support"),  # jarir — "my Jarir account"
    ("خدمة الطلب", "account_support"),  # jarir — "order service"
    ("بطاقة خصم جرير", "account_support"),  # jarir — "Jarir discount card"
    ("تسجيل حساب جديد", "account_support"),  # jarir — "register new account"
    ("خدمة استبدال جرير", "account_support"),  # jarir — "Jarir exchange service"
    ("عربة التسوق", "navigational"),  # chewy — "shopping cart"
    ("تجربة المستخدم", "generic"),  # chewy — "user experience"
    ("شحن مجاني", "generic"),  # chewy — "free shipping"
    ("عروض الشحن", "generic"),  # chewy — "shipping offers"
    ("عروض وخصومات", "generic"),  # chewy — "offers and discounts"
]


def test_round2_confirmed_non_discovery_patterns_are_all_rejected():
    for topic, expected_type in _ROUND2_NON_DISCOVERY_TOPICS:
        result = score_intent_quality(
            topic=topic, category=None, commercial_stage=None, source=IntentSource.ai_expansion,
            catalog_tokens=set(), brand_tokens=set(),
        )
        assert result.is_accepted is False, f"{topic!r} should be rejected, got accepted with type {result.intent_type!r}"
        assert result.intent_type == expected_type, f"{topic!r} expected type {expected_type!r}, got {result.intent_type!r}"


def test_generic_phrase_is_accepted_once_it_carries_real_catalog_specificity():
    """The same generic word ('توصيل'/'delivery') paired with a real
    catalog term is NOT generic — catalog overlap makes it a specific,
    measurable query, exactly the distinction a flat blacklist can't draw."""
    result = score_intent_quality(
        topic="توصيل سريع للقهوة المختصة", category=None, commercial_stage=None, source=IntentSource.ai_expansion,
        catalog_tokens={"القهوة", "قهوة", "المختصة"}, brand_tokens=set(),
    )
    assert result.is_accepted is True


def test_login_is_still_rejected_as_account_support_not_a_flat_navigation_bucket():
    result = score_intent_quality(
        topic="تسجيل الدخول", category=None, commercial_stage=None, source=IntentSource.ai_expansion,
        catalog_tokens=set(), brand_tokens=set(),
    )
    assert result.is_accepted is False
    assert result.intent_type == "account_support"


def test_apply_quality_gate_excludes_navigational_and_generic_types_from_measurement(session):
    """End-to-end through the real gate entry point: the returned
    (measurable) subset never includes navigational/account_support/
    policy/generic/invalid types, matching requirement C."""
    store, run = _make_store_and_run(session)
    topics_and_expected_acceptance = [
        ("أدوات تحضير القهوة", True),
        ("تسوق آمن", False),
        ("حسابي في المتجر", False),
        ("سياسة الخصوصية", False),
        ("سلة التسوق", False),
    ]
    intents = [
        Intent(
            store_id=store.id, research_run_id=run.id, topic=topic, country="sa", language="ar",
            source=IntentSource.ai_expansion,
        )
        for topic, _ in topics_and_expected_acceptance
    ]
    for intent in intents:
        session.add(intent)
    session.commit()

    accepted = apply_quality_gate(session, intents, store.id)
    accepted_topics = {i.topic for i in accepted}

    for topic, expected in topics_and_expected_acceptance:
        assert (topic in accepted_topics) == expected, f"{topic!r} acceptance mismatch"

    all_intents = session.exec(select(Intent).where(Intent.store_id == store.id)).all()
    for intent in all_intents:
        if not intent.is_accepted:
            assert intent.intent_type in {"navigational", "account_support", "policy", "generic", "invalid"}
