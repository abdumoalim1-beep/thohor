from __future__ import annotations

from html import unescape
from urllib.parse import urlparse

from app.api.schemas import (
    BusinessInfoItem,
    ProductCategoryPreviewItem,
    StoreProfileProduct,
)
from app.models.research import AgentRun, RunStatus

MIN_CLASSIFICATION_CONFIDENCE_FOR_READY = 0.4
"""Same threshold as MIN_INTENT_CONFIDENCE (opportunities/detectors.py),
reused deliberately for consistency rather than re-derived — not yet
empirically tuned against this specific model's confidence distribution."""

MIN_IDENTITY_CONFIDENCE_FOR_PROVISIONAL = 0.40
"""Same numeric bar as MIN_CLASSIFICATION_CONFIDENCE_FOR_READY, reused
deliberately — this is the confidence floor a web-search-resolved
StoreIdentity must clear before registration is allowed to proceed."""


def _resolve_from_crawl_classification(
    *,
    crawl_run: AgentRun | None,
    classification_run: AgentRun | None,
    classification_confidence: float | None,
    classification_skipped: bool,
) -> str:
    """The original (pre-identity-decoupling) crawl+classification-only
    state machine — preserved verbatim as the fallback path for runs that
    never went through identity resolution (e.g. monitoring runs, or any
    run predating Phase 1), and as the source for translating a stuck
    crawl/classification outcome into the new stage vocabulary below.
    """
    if crawl_run is None:
        return "pending"
    if crawl_run.status == RunStatus.failed:
        return "failed"
    if crawl_run.status != RunStatus.completed:
        return "pending"
    if classification_run is None or classification_run.status not in (RunStatus.completed, RunStatus.failed):
        return "partial"
    if classification_skipped:
        return "low_confidence"
    if classification_confidence is not None and classification_confidence < MIN_CLASSIFICATION_CONFIDENCE_FOR_READY:
        return "low_confidence"
    return "ready"


def resolve_understanding_stage(
    *,
    crawl_run: AgentRun | None,
    classification_run: AgentRun | None,
    classification_confidence: float | None,
    classification_skipped: bool,
    identity_run: AgentRun | None = None,
    identity_confidence: float | None = None,
    identity_brand_name: str | None = None,
    identity_skipped: bool = False,
    catalog_status: str = "pending",
) -> str:
    """The single source of truth for understanding_stage.

    identity_run defaults to None so every caller/test written before
    identity decoupling keeps returning exactly the old 5-value stage set
    (pending/partial/ready/low_confidence/failed) unmodified — this
    function only switches to the new 7-value machine
    (resolving_identity/provisional/catalog_scanning/ready/
    needs_confirmation/catalog_blocked/failed) once a real identity_run is
    passed in. "ready" always means "completed AND trustworthy," never
    just "the task didn't raise."
    """
    if identity_run is None:
        return _resolve_from_crawl_classification(
            crawl_run=crawl_run,
            classification_run=classification_run,
            classification_confidence=classification_confidence,
            classification_skipped=classification_skipped,
        )

    if crawl_run is None or identity_run.status == RunStatus.running:
        return "resolving_identity"
    if crawl_run.status == RunStatus.failed and identity_run.status != RunStatus.completed:
        return "failed"

    identity_ok = (
        identity_confidence is not None
        and identity_confidence >= MIN_IDENTITY_CONFIDENCE_FOR_PROVISIONAL
        and bool(identity_brand_name)
    )

    if not identity_ok:
        if identity_run.status == RunStatus.completed and not identity_skipped:
            # Identity resolution finished but landed below the confidence
            # bar (or without a usable brand_name) — a plausible result
            # exists, the user just needs to confirm/edit it. Never a wall.
            return "needs_confirmation"
        # identity_skipped=True means web_search never actually produced a
        # result (e.g. 'web_search_unavailable_or_failed') — AgentRun.status
        # is still "completed" for a skip (it's a normal, non-exceptional
        # outcome), which used to be indistinguishable here from "genuinely
        # tried and landed low-confidence," incorrectly forcing every
        # web_search-outage store into needs_confirmation with a blank
        # display_name even when crawl+classification alone had already
        # produced a confident, complete result. Confirmed live on
        # modernsupply.com.sa: classification_confidence=0.85 with real
        # categories/products, but stuck at needs_confirmation for this
        # reason alone.
        # Identity resolution itself failed/was skipped — fall back to
        # whatever the crawl+classification path would have said, mapped
        # onto the new vocabulary instead of the old one.
        legacy_stage = _resolve_from_crawl_classification(
            crawl_run=crawl_run,
            classification_run=classification_run,
            classification_confidence=classification_confidence,
            classification_skipped=classification_skipped,
        )
        if legacy_stage == "pending":
            return "resolving_identity"
        if legacy_stage == "partial":
            return "catalog_scanning"
        if legacy_stage == "failed":
            return "failed"
        if legacy_stage == "low_confidence":
            return "needs_confirmation"
        # legacy_stage == "ready" — crawl+classification alone reached a
        # confident, complete result even though identity resolution
        # contributed nothing (skipped or failed). Trust it, exactly as the
        # pre-identity-decoupling system always did for this same data —
        # forcing a confirm screen here would show no actual name to
        # confirm (display_name is null with no identity_brand_name),
        # which is strictly worse than proceeding with the real result
        # crawl+classification already produced. Confirmed live on
        # modernsupply.com.sa (see the identity_skipped comment above).
        return "ready"

    if catalog_status in ("blocked", "failed"):
        return "catalog_blocked"
    if catalog_status == "scanning":
        return "catalog_scanning"
    if catalog_status in ("ready", "partial"):
        return "ready"
    return "provisional"

_INFO_RULES = (
    ("shipping", "التوصيل والشحن", ("شحن", "توصيل", "shipping", "delivery")),
    ("payment", "الدفع", ("دفع", "payment", "pay")),
    ("returns", "الاستبدال والاسترجاع", ("استبدال", "استرجاع", "return", "refund")),
    ("location", "الموقع والفروع", ("فروع", "موقعنا", "location", "branches")),
    ("contact", "التواصل", ("تواصل", "اتصل", "contact", "whatsapp")),
)
_SOCIAL_HOSTS = {"instagram.com", "tiktok.com", "snapchat.com", "x.com", "twitter.com", "facebook.com"}
_PRODUCT_CATEGORY_RULES = (
    ("مكياج العيون", ("مسكرا", "ماسكرا", "حواجب", "آيلاينر", "ايلاينر", "eyeliner", "mascara", "brow")),
    ("مكياج الوجه", ("بودرة", "بودره", "بلاشر", "فاونديشن", "كونسيلر", "powder", "blush", "foundation")),
    ("مكياج الشفاه", ("روج", "شفاه", "lipstick", "lip gloss")),
    ("إكسسوارات الشعر", ("ربطة شعر", "ربطه شعر", "توكه", "مشبك شعر", "hair tie", "hair clip")),
)


def build_category_previews(
    primary_categories: list[str], catalog_categories: list[tuple[str, str | None, int]],
    products: list[StoreProfileProduct], classification_confidence: float | None,
) -> list[ProductCategoryPreviewItem]:
    previews: list[ProductCategoryPreviewItem] = []
    seen: set[str] = set()
    for index, (name, url, count) in enumerate(catalog_categories):
        key = name.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        previews.append(ProductCategoryPreviewItem(
            name=unescape(name), url=url, product_count=count, confidence=1.0,
            source="catalog", image_url=products[index % len(products)].image_url if products else None,
        ))
    # Product names and images are direct observed evidence. They can support
    # a useful category preview, but never a total catalog count.
    for category_name, keywords in _PRODUCT_CATEGORY_RULES:
        matches = [product for product in products if any(keyword in product.name.casefold() for keyword in keywords)]
        key = category_name.casefold()
        if not matches or key in seen:
            continue
        seen.add(key)
        previews.append(ProductCategoryPreviewItem(
            name=category_name, product_count=None, confidence=0.85,
            source="observed_products", image_url=next((item.image_url for item in matches if item.image_url), None),
        ))
    for name in primary_categories:
        key = name.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        index = len(previews)
        previews.append(ProductCategoryPreviewItem(
            name=unescape(name), product_count=None, confidence=classification_confidence,
            source="classification", image_url=products[index % len(products)].image_url if products else None,
        ))
    return previews[:8]


def build_business_info(page_links: list[tuple[str, str]]) -> list[BusinessInfoItem]:
    items: list[BusinessInfoItem] = []
    seen_kinds: set[str] = set()
    for title, url in page_links:
        haystack = f"{unescape(title)} {url}".casefold()
        host = (urlparse(url).hostname or "").removeprefix("www.").casefold()
        matched = next(((kind, label) for kind, label, words in _INFO_RULES if any(word in haystack for word in words)), None)
        if matched is None and host in _SOCIAL_HOSTS:
            matched = ("social", "حسابات التواصل")
        if matched is None or matched[0] in seen_kinds:
            continue
        seen_kinds.add(matched[0])
        items.append(BusinessInfoItem(kind=matched[0], label=matched[1], url=url))
    return items
