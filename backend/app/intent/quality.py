import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models.catalog import Brand, Category, Product
from app.models.intent import CommercialStage, Intent, IntentSource
from app.models.stable_intent import normalize_topic

INTENT_QUALITY_THRESHOLD = 0.5
MAX_NATURAL_WORD_COUNT = 9
NEAR_DUPLICATE_JACCARD_THRESHOLD = 0.6

# Part R2-F2 (Round 2 remediation) — root cause confirmed across all 4
# Round 2 stores: generic/navigational/account/policy phrases ("تسجيل
# حساب جديد", "تسوق آمن", "عربة التسوق", "بطاقة خصم جرير"...) kept
# reaching acceptance because the old gate only checked a small, flat,
# exact-match NAV_LABELS set — it demonstrably rejected some shapes
# (e.g. "تسجيل الدخول") while missing structurally identical ones just
# because the exact phrase wasn't enumerated. This rewrite classifies
# every intent into one of nine types BEFORE deciding acceptance, using
# pattern families (substring match across many phrasings) plus catalog-
# overlap structure — never a single flat blacklist — so a new phrasing
# of an already-known non-discovery shape is caught without needing its
# own dedicated entry.

# --- account/support: logging in, order status, loyalty, customer service ---
_ACCOUNT_SUPPORT_PATTERNS = [
    "تسجيل الدخول", "تسجيل دخول", "دخول الحساب", "إنشاء حساب", "انشاء حساب",
    "تسجيل حساب", "حسابي في", "حسابي", "خدمة العملاء", "الدعم الفني", "دعم العملاء",
    "تواصل معنا", "اتصل بنا", "خدمة الطلب", "تتبع الطلب", "حالة الطلب", "تتبع الشحنة",
    "خدمة استبدال", "طلب استبدال", "طلب إرجاع", "بطاقة خصم", "بطاقة هدايا", "بطاقة هدية",
    "برنامج الولاء", "عضوية", "الاشتراك في النشرة",
    "login", "log in", "sign in", "sign up", "register", "create account", "my account",
    "customer service", "customer support", "contact us", "track order", "order status",
    "track shipment", "exchange service", "return request", "loyalty program", "membership",
    "gift card", "newsletter signup",
]
# --- policy: legal/informational-about-the-store-itself pages, never a product search ---
_POLICY_PATTERNS = [
    "سياسة الخصوصية", "سياسة الاستخدام", "الشروط والأحكام", "سياسة الإرجاع", "سياسة الشحن",
    "سياسة الاستبدال", "سياسة ملفات الارتباط",
    "privacy policy", "terms of service", "terms and conditions", "return policy",
    "shipping policy", "cookie policy", "exchange policy",
]
# --- navigational: site chrome, not a search query at all ---
_NAVIGATIONAL_PATTERNS = [
    "الرئيسية", "من نحن", "سلة التسوق", "عربة التسوق", "عربة الشراء", "المفضلة",
    "قائمة الرغبات", "خريطة الموقع",
    "home page", "homepage", "about us", "shopping cart", "cart", "wishlist",
    "favorites", "site map",
]
# --- generic: real words, zero discovery value — a marketing tagline or an
# abstract UX concept, not something a buyer searches for a specific need.
_ABSTRACT_NONDISCOVERY_PATTERNS = [
    "تجربة المستخدم", "تجربة التسوق", "سهولة الاستخدام", "سهولة التسوق",
    "user experience", "ease of use", "shopping experience",
]
_GENERIC_COMMERCE_WORDS = {
    "تسوق", "شراء", "شحن", "توصيل", "دفع", "عروض", "خصومات", "خصم", "آمن", "أمان",
    "سريع", "سريعة", "سهل", "سهلة", "مريح", "مريحة", "مجاني", "مجانية", "جديد", "جديدة",
    "جودة", "أفضل", "افضل", "رخيص", "رخيصة", "منخفض", "منخفضة", "اونلاين", "أونلاين",
    "الإنترنت", "الانترنت", "إنترنت", "انترنت", "عبر", "الآن", "الان",
    "shopping", "shop", "buy", "buying", "shipping", "delivery", "payment", "offers",
    "offer", "discount", "discounts", "safe", "secure", "fast", "easy", "comfortable",
    "free", "new", "quality", "best", "cheap", "low", "price", "prices", "online",
}
COMPARISON_MARKERS = ["مقارنة", "أفضل", "افضل", " أو ", " vs ", "مقابل"]
PROBLEM_MARKERS = ["مشكلة", "كيف أحل", "كيف احل", "لا يعمل", "عطل", "حل مشكلة"]
LOCAL_MARKERS = ["بالقرب مني", "قريب مني", "في الرياض", "في جدة", "في الدمام", "أقرب فرع", "فروع"]
INFORMATIONAL_MARKERS = ["ما هو", "ما هي", "لماذا", "متى يجب", "كيف يعمل", "تعريف"]
ARABIC_STOPWORDS = {
    "من", "في", "على", "الى", "إلى", "و", "أو", "او", "ما", "هو", "هي", "وش", "ايش", "أي",
    "لي", "لك", "عن", "مع", "هذا", "هذه", "التي", "الذي", "يا",
}

# The 5 types that carry real, measurable discovery value — everything
# else is excluded from SERP/AI-visibility measurement by default (Part
# R2-F2 requirement C).
_MEASURABLE_INTENT_TYPES = frozenset(
    {"commercial_discovery", "category_discovery", "product_discovery", "informational_commercial", "brand"}
)


@dataclass
class IntentQualityResult:
    score: float
    reason: str
    intent_type: str
    is_accepted: bool


def _word_count(text: str) -> int:
    return len(text.split())


def _looks_like_scraped_title(topic: str) -> bool:
    """Catches exactly the G-A failure mode: page/product titles like
    'منافيخ هواء كهربائية | بلاور ... | بوش، هيونداي وسكيل | إكسترا السعودية'
    — pipe-separated or heavily comma-enumerated strings nobody types or
    speaks as a search query."""
    if "|" in topic:
        return True
    return topic.count(",") >= 2 or topic.count("،") >= 2


def _matches_any(normalized_topic: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        if normalize_topic(pattern) in normalized_topic:
            return pattern
    return None


def _content_tokens(text: str) -> set[str]:
    normalized = normalize_topic(text)
    return {t for t in normalized.split() if t not in ARABIC_STOPWORDS and len(t) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Arabic attaches definite-article/conjunction/preposition clitics directly
# to the following word with no space ("الشحن", "وخصومات") — normalize_topic
# doesn't split these, so a bare set-membership check misses them unless we
# strip the clitic first. Longest prefixes checked first so "بالشحن" doesn't
# wrongly match on "ب" alone and leave "الشحن" unstripped.
_ARABIC_CLITIC_PREFIXES = ("بال", "كال", "وال", "فال", "لل", "ال", "و", "ف", "ب", "ك", "ل")


def _strip_arabic_clitics(token: str) -> str:
    for prefix in _ARABIC_CLITIC_PREFIXES:
        if token.startswith(prefix) and len(token) > len(prefix) + 1:
            return token[len(prefix):]
    return token


def _is_generic_marketing_phrase(topic_tokens: set[str], catalog_tokens: set[str], brand_tokens: set[str]) -> bool:
    """True when every content word in the topic is a generic commerce
    adjective/noun ('safe', 'fast', 'shipping', 'offers'...) and none of
    them names anything the store actually sells — 'تسوق آمن' ('safe
    shopping'), 'شحن مجاني' ('free shipping'), 'عروض وخصومات' ('offers and
    discounts'). A topic that mixes a generic word with a real catalog
    term ('توصيل سريع للقهوة المختصة') is NOT generic — the catalog
    overlap makes it a real, specific query."""
    if not topic_tokens:
        return False
    if topic_tokens & catalog_tokens or topic_tokens & brand_tokens:
        return False
    normalized_tokens = {_strip_arabic_clitics(t) for t in topic_tokens}
    return normalized_tokens <= _GENERIC_COMMERCE_WORDS


def classify_intent_type(topic: str, category: str | None, commercial_stage: CommercialStage | None) -> str:
    """Legacy informational-vs-commercial-shape classifier — still used to
    label the *accepted* subset (comparison/problem_solution/local/
    informational/commercial_category/product_discovery), now called only
    after the R2-F2 exclusion checks in score_intent_quality have already
    ruled out navigational/account/policy/generic/invalid."""
    for marker in COMPARISON_MARKERS:
        if marker in topic:
            return "informational_commercial"
    for marker in PROBLEM_MARKERS:
        if marker in topic:
            return "informational_commercial"
    for marker in LOCAL_MARKERS:
        if marker in topic:
            return "informational_commercial"
    for marker in INFORMATIONAL_MARKERS:
        if marker in topic:
            return "informational_commercial"
    if commercial_stage == CommercialStage.purchase:
        return "product_discovery"
    if category:
        return "category_discovery"
    return "commercial_discovery"


def score_intent_quality(
    *,
    topic: str,
    category: str | None,
    commercial_stage: CommercialStage | None,
    source: IntentSource,
    catalog_tokens: set[str],
    brand_tokens: set[str],
) -> IntentQualityResult:
    stripped = topic.strip()
    if not stripped:
        return IntentQualityResult(0.0, "invalid: empty topic", "invalid", False)

    normalized = normalize_topic(stripped)
    topic_tokens = _content_tokens(stripped)

    # Part R2-F2 — classification BEFORE scoring, via pattern families
    # (never a single flat blacklist): each family covers many phrasings
    # of the same underlying non-discovery shape, so a new phrasing of an
    # already-known pattern (e.g. any "خدمة استبدال X" variant) is caught
    # without a dedicated entry per store.
    match = _matches_any(normalized, _ACCOUNT_SUPPORT_PATTERNS)
    if match:
        return IntentQualityResult(0.0, f"account_navigation: matches account/support pattern {match!r}", "account_support", False)

    match = _matches_any(normalized, _POLICY_PATTERNS)
    if match:
        return IntentQualityResult(0.0, f"policy_page: matches policy/legal pattern {match!r}", "policy", False)

    match = _matches_any(normalized, _NAVIGATIONAL_PATTERNS)
    if match:
        return IntentQualityResult(0.0, f"site_navigation: matches navigational pattern {match!r}", "navigational", False)

    if _looks_like_scraped_title(stripped):
        return IntentQualityResult(
            0.0, "invalid: reads like a scraped page/product title (pipe or multi-item enumeration), not a search query",
            "invalid", False,
        )

    match = _matches_any(normalized, _ABSTRACT_NONDISCOVERY_PATTERNS)
    is_brand = bool(brand_tokens & topic_tokens)
    overlaps_catalog = bool(catalog_tokens & topic_tokens)
    if match and not overlaps_catalog and not is_brand:
        return IntentQualityResult(0.0, f"too_generic: abstract non-discovery concept {match!r}, no catalog specificity", "generic", False)

    if _is_generic_marketing_phrase(topic_tokens, catalog_tokens, brand_tokens):
        return IntentQualityResult(
            0.0, "too_generic: every word is a generic commerce adjective/noun with no catalog specificity", "generic", False,
        )

    reasons: list[str] = []
    score = 1.0

    word_count = _word_count(stripped)
    if word_count > MAX_NATURAL_WORD_COUNT:
        score -= 0.5
        reasons.append(f"too long for a natural spoken/typed query ({word_count} words)")

    if word_count <= 1 and not category:
        score -= 0.2
        reasons.append("single generic word with no catalog category context")

    # deterministic_catalog intents are the category/product name itself —
    # they can never fail this check, only ai_expansion intents can drift
    # away from what the store actually sells.
    if source == IntentSource.ai_expansion and not overlaps_catalog and not is_brand and word_count >= 3:
        score -= 0.2
        reasons.append("non_discovery_intent: no overlap with the store's own catalog categories/products")

    score = max(0.0, min(1.0, score))
    intent_type = "brand" if is_brand else classify_intent_type(stripped, category, commercial_stage)
    reason = "; ".join(reasons) if reasons else "passes deterministic quality checks"
    is_accepted = score >= INTENT_QUALITY_THRESHOLD and intent_type in _MEASURABLE_INTENT_TYPES
    return IntentQualityResult(score=score, reason=reason, intent_type=intent_type, is_accepted=is_accepted)


def _dedupe_near_duplicates(scored: list[tuple[Intent, IntentQualityResult]]) -> None:
    """Among this run's still-accepted intents, keeps the highest-scoring
    member of each near-duplicate cluster (Jaccard token overlap on
    content words, e.g. 'أفضل قهوة مختصة' vs 'وش أفضل متجر قهوة مختصة؟')
    and downgrades the rest — mutates the IntentQualityResult objects in
    place."""
    accepted = sorted((pair for pair in scored if pair[1].is_accepted), key=lambda pair: pair[1].score, reverse=True)
    kept_tokens: list[set[str]] = []
    for intent, result in accepted:
        tokens = _content_tokens(intent.topic)
        if any(_jaccard(tokens, kept) >= NEAR_DUPLICATE_JACCARD_THRESHOLD for kept in kept_tokens):
            result.is_accepted = False
            result.reason = (result.reason + "; near-duplicate of an already-accepted intent this run").strip("; ")
        else:
            kept_tokens.append(tokens)


def apply_quality_gate(session: Session, intents: list[Intent], store_id: uuid.UUID) -> list[Intent]:
    """Part G-B1 / R2-F2 entry point — call once, right after intent
    generation and before anything (SERP, prompt families) consumes the
    list. Every intent is scored and persisted (is_accepted/quality_score/
    quality_reason/intent_type set on the row, nothing deleted); only the
    accepted subset — restricted to the 5 measurable intent types — is
    returned for the Control/Research Set to use. Navigational/account/
    policy/generic intents never reach SERP or AI-visibility measurement.
    """
    if not intents:
        return []

    categories = session.exec(select(Category).where(Category.store_id == store_id)).all()
    products = session.exec(select(Product).where(Product.store_id == store_id)).all()
    catalog_tokens: set[str] = set()
    for category in categories:
        catalog_tokens |= _content_tokens(category.name or "")
    for product in products:
        catalog_tokens |= _content_tokens(product.name or "")

    brand = session.exec(select(Brand).where(Brand.store_id == store_id)).first()
    brand_tokens: set[str] = set()
    if brand:
        brand_tokens |= _content_tokens(brand.name or "")
        for alias in brand.aliases:
            brand_tokens |= _content_tokens(alias)

    scored: list[tuple[Intent, IntentQualityResult]] = [
        (
            intent,
            score_intent_quality(
                topic=intent.topic,
                category=intent.category,
                commercial_stage=intent.commercial_stage,
                source=intent.source,
                catalog_tokens=catalog_tokens,
                brand_tokens=brand_tokens,
            ),
        )
        for intent in intents
    ]

    _dedupe_near_duplicates(scored)

    for intent, result in scored:
        intent.intent_type = result.intent_type
        intent.quality_score = result.score
        intent.quality_reason = result.reason
        intent.is_accepted = result.is_accepted
        session.add(intent)
    session.commit()

    return [intent for intent, result in scored if result.is_accepted]
