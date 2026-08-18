import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.core.domain import matches_curated_domain, registered_domain
from app.core.urls import normalize_hostname
from app.models.ai_visibility import AIVisibilityObservation
from app.models.catalog import Category, Product
from app.models.competitor import Competitor, CompetitorRelationship
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.intent import Intent
from app.models.serp import SerpObservation
from app.models.stable_intent import normalize_topic

MIN_SHARED_INTENTS_FOR_DIRECT = 2
DIRECT_CONFIDENCE = 0.7
RETAILER_CONFIDENCE = 0.4
UNKNOWN_CONFIDENCE = 0.15

# Part R2-F3 (Round 2 remediation) — confirmed root cause: a domain became
# "direct_competitor" the moment it shared >=2 intents with the store AND
# had *any single word* in common between its domain/SERP-title text and
# the store's catalog/intent tokens. Since catalog_tokens is partly built
# from intent *topics* (see the loop below), and a generic query like
# "تسوق آمن" ("safe shopping") contributes the word "آمن" to catalog_tokens,
# any unrelated domain whose SERP title happened to also say "آمن" —
# Kaspersky's antivirus listing, a pharmacy app's "secure checkout" copy —
# cleared that bar. Confirmed in Round 2 on 3 of 4 stores (Kaspersky/
# QuestionPro on chewy.com, EF Education/iHerb on alsaifgallery.com,
# pharmacy/food-delivery apps on glossier.com — the last compounded by the
# separate R2-F1 locale bug). This set excludes exactly the same generic
# commerce/marketing vocabulary app.intent.quality's quality gate already
# treats as non-discovery-specific, so a coincidental match on a common
# word like "جديد"/"أفضل"/"سريع" can never by itself read as evidence of a
# real commercial intersection — a deliberate, small, independent copy
# rather than a cross-import, matching this module's own existing
# precedent of keeping its own _content_tokens rather than importing
# app.intent.quality's private helpers.
_GENERIC_OVERLAP_NOISE_WORDS = {
    "تسوق", "شراء", "شحن", "توصيل", "دفع", "عروض", "خصومات", "خصم", "آمن", "أمان",
    "سريع", "سريعة", "سهل", "سهلة", "مريح", "مريحة", "مجاني", "مجانية", "جديد", "جديدة",
    "جودة", "أفضل", "افضل", "رخيص", "رخيصة", "منخفض", "منخفضة", "اونلاين", "أونلاين",
    "الإنترنت", "الانترنت", "إنترنت", "انترنت", "عبر", "الآن", "الان",
    "shopping", "shop", "buy", "buying", "shipping", "delivery", "payment", "offers",
    "offer", "discount", "discounts", "safe", "secure", "fast", "easy", "comfortable",
    "free", "new", "quality", "best", "cheap", "low", "price", "prices", "online",
}
# At least this many *specific* (non-generic) shared words are required
# before a category/title-text overlap counts as commercial-intersection
# evidence — a single coincidental word was exactly the confirmed bug.
MIN_MEANINGFUL_OVERLAP_TOKENS = 2
# Overlap against the store's *own catalog* (Category/Product names) is a
# real commercial signal. Overlap against an *intent topic's own words* is
# much weaker and easy to game: any SERP result answering a query tends to
# echo that query's own words in its title regardless of what the result
# actually sells (confirmed case: alsaifgallery.com's own accepted intent
# "منتجات صديقة للبيئة" put those exact words into catalog_tokens, so
# ef.com's SERP snippet for that same query trivially "overlapped" by
# echoing the query back — ef.com sells nothing eco-friendly). When no real
# catalog exists at all (Part G-B6's original fallback case), intent-topic
# overlap is still used, but needs more shared words to compensate for
# being the weaker, self-referential signal.
MIN_MEANINGFUL_OVERLAP_TOKENS_TOPIC_ONLY = 3
# relevance_score must clear this before a domain can ever be promoted to
# direct_competitor — see assess_vertical_relevance.
DIRECT_RELEVANCE_THRESHOLD = 0.5

# Part R3.2 (Round 1 remediation) — the full role taxonomy. A domain
# appearing in Google/AI answers is not automatically a "competitor";
# these are the well-known, finite, non-competitor categories, matched by
# *registered domain* (Part R3.1 — suffix-aware, so a regional/mobile
# subdomain like ar.wikipedia.org or m.facebook.com is caught exactly like
# the bare domain, unlike the old exact-string check that only ever
# stripped a literal "www." prefix and missed ar.wikipedia.org entirely).
# This list grows the same deliberate, finite way it always has (Part
# G-B2) — one well-known *category* of site at a time, not one arbitrary
# per-store domain at a time; see Part R3.3 below for the part of
# classification that has to generalize instead of being curated.
MARKETPLACE_DOMAINS = frozenset({
    "amazon.sa", "amazon.com", "amazon.ae", "noon.com", "souq.com", "haraj.com.sa",
    "opensooq.com", "jumia.com.sa", "aliexpress.com", "temu.com", "ebay.com",
})
# Part R3 — separate from retail marketplaces on purpose: a B2B wholesale/
# manufacturer-sourcing platform (Round 1 found arabic.alibaba.com and
# sa.made-in-china.com misclassified as direct retail competitors for
# allbirds.com) competes with *suppliers*, not with a retail storefront.
WHOLESALE_DOMAINS = frozenset({
    "alibaba.com", "made-in-china.com", "globalsources.com", "dhgate.com", "indiamart.com",
})
SOCIAL_DOMAINS = frozenset({
    "facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com", "pinterest.com",
    "snapchat.com", "linkedin.com", "threads.net",
})
# Part R3.2 — split out from "social": community Q&A/discussion, not a
# broadcast social-media profile.
FORUM_DOMAINS = frozenset({"reddit.com", "quora.com"})
VIDEO_DOMAINS = frozenset({"youtube.com", "youtu.be", "vimeo.com"})
# Part R3 — general reference/informational sites. wikipedia.org is the
# confirmed Round 1 case (was missed entirely due to the subdomain-
# matching bug, not a missing curated entry); webteb.com/altibbi.com are
# the confirmed "health content site pulled in as a competitor by a
# tangential intent" case from the same round. A more general content-
# classification heuristic (distinguishing any informational site from a
# retailer without curation) is a Future Candidate, not attempted here —
# see the R13 remediation report.
PUBLISHER_DOMAINS = frozenset({
    "wikipedia.org", "medium.com", "genius.com", "webteb.com", "altibbi.com",
})
APP_STORE_DOMAINS = frozenset({"apps.apple.com", "play.google.com"})
# Part R3 — Round 1 confirmed google.com itself classified as a direct
# competitor for roastinghouse.sa (a SERP-own feature — "People also ask",
# Maps, etc. — surfacing google.com as a result domain, not a real
# business). Unlike APP_STORE_DOMAINS these are bare registered domains
# (any subdomain matches), since the whole of google.com/bing.com is the
# search engine, not one specific subpath.
SEARCH_ENGINE_DOMAINS = frozenset({"google.com", "bing.com", "yahoo.com"})
GOVERNMENT_TLD_MARKERS = (".gov.sa", ".gov")
EDUCATIONAL_TLD_MARKERS = (".edu.sa", ".edu")

_CURATED_DOMAIN_ROLES: tuple[tuple[frozenset[str], str, float, str], ...] = (
    (MARKETPLACE_DOMAINS, "marketplace", 0.95, "هو موقع سوق إلكتروني عام معروف (marketplace)"),
    (WHOLESALE_DOMAINS, "wholesale", 0.95, "منصة توريد/تجارة بالجملة بين الشركات (B2B)، وليس منافسًا للتجزئة"),
    (SOCIAL_DOMAINS, "social", 0.95, "منصة تواصل اجتماعي"),
    (FORUM_DOMAINS, "forum", 0.9, "منتدى/منصة أسئلة وأجوبة مجتمعية"),
    (VIDEO_DOMAINS, "video", 0.95, "منصة فيديو"),
    (PUBLISHER_DOMAINS, "publisher", 0.9, "موقع نشر/مرجع عام"),
    (APP_STORE_DOMAINS, "irrelevant", 0.9, "صفحة متجر تطبيقات، ليست منافسًا تجاريًا"),
    (SEARCH_ENGINE_DOMAINS, "irrelevant", 0.95, "نطاق محرك بحث نفسه (ميزة SERP)، وليس منافسًا تجاريًا"),
)


def classify_known_domain(domain: str) -> tuple[str, float, str] | None:
    """First pass — high-confidence deterministic lookup. Returns None when
    the domain isn't a known non-competitor category, meaning it needs the
    catalog-overlap heuristic instead. Matching is by registered domain
    (Part R3.1), so a curated entry like "wikipedia.org" also catches
    ar.wikipedia.org, en.wikipedia.org, www.wikipedia.org, m.wikipedia.org
    — any subdomain — not just an exact string match."""
    # matches_curated_domain needs the *original* hostname (subdomain
    # intact) — a couple of curated entries (apps.apple.com) are
    # themselves subdomain-specific, not bare registrable domains, and
    # would never match if the subdomain were stripped first.
    hostname = domain.strip().lower()
    bare = registered_domain(domain)  # only for the message text / TLD checks below

    for curated_set, role, confidence, reason_suffix in _CURATED_DOMAIN_ROLES:
        if any(matches_curated_domain(hostname, entry) for entry in curated_set):
            return role, confidence, f"{bare} {reason_suffix}"
    if any(bare.endswith(marker) for marker in EDUCATIONAL_TLD_MARKERS):
        return "educational", 0.9, f"{bare} نطاق تعليمي"
    if any(bare.endswith(marker) for marker in GOVERNMENT_TLD_MARKERS):
        return "government", 0.9, f"{bare} نطاق حكومي"
    return None


def _content_tokens(text: str) -> set[str]:
    normalized = normalize_topic(text)
    return {t for t in normalized.split() if len(t) > 1}


def _specific_tokens(tokens: set[str]) -> set[str]:
    """Strips generic commerce/marketing vocabulary before it can ever
    count as competitive-overlap evidence (Part R2-F3)."""
    return {t for t in tokens if t not in _GENERIC_OVERLAP_NOISE_WORDS}


@dataclass
class RelevanceAssessment:
    """Part R2-F3 — the new, independent pipeline stage between 'a domain
    co-occurred with the store' and 'this domain is a direct competitor'.
    Never a domain-specific blacklist/allowlist — every field here is
    computed the same general way for any domain."""

    relevance_score: float
    reasons: list[str] = field(default_factory=list)
    classification_confidence: float = UNKNOWN_CONFIDENCE
    is_eligible_for_direct: bool = False


def assess_vertical_relevance(
    *,
    domain_tokens: set[str],
    title_tokens: set[str],
    real_catalog_tokens: set[str],
    intent_topic_tokens: set[str] = frozenset(),
    shared_intent_count: int,
) -> RelevanceAssessment:
    """Combines category/product-text overlap (SERP title + domain text vs.
    the store's own vocabulary, generic words excluded) with intent overlap
    (how many distinct search intents this domain appeared for) into one
    relevance_score. A domain is only eligible for direct_competitor when
    BOTH signals clear their own bar — promotion needs positive evidence of
    a real commercial intersection, not co-occurrence alone.

    `real_catalog_tokens` (Category/Product names — what the store actually
    sells) and `intent_topic_tokens` (the search query's own words) are
    deliberately separate, not merged: any SERP result answering a query
    tends to echo that query's own words in its title regardless of what it
    actually sells, so topic-word overlap alone is a much weaker, easier-
    to-game signal (confirmed case: ef.com's snippet for alsaifgallery.com's
    own "منتجات صديقة للبيئة" intent echoed those exact words back without
    ef.com selling anything eco-friendly). Topic overlap only counts when
    no real catalog exists at all (Part G-B6's original empty-catalog
    fallback), and then needs more shared words to compensate."""
    reasons: list[str] = []

    specific_domain_title = _specific_tokens(domain_tokens | title_tokens)
    real_overlap = _specific_tokens(real_catalog_tokens) & specific_domain_title
    topic_overlap = _specific_tokens(intent_topic_tokens) & specific_domain_title

    if real_catalog_tokens:
        overlap_tokens = real_overlap
        min_overlap_required = MIN_MEANINGFUL_OVERLAP_TOKENS
        if overlap_tokens:
            reasons.append(f"تقاطع كلمات محددة مع كتالوج المتجر الفعلي: {'، '.join(sorted(overlap_tokens)[:5])}")
    else:
        # No Category/Product rows at all (Part G-B6 empty-catalog case) —
        # topic-word overlap is all that's available, so demand more of it.
        overlap_tokens = topic_overlap
        min_overlap_required = MIN_MEANINGFUL_OVERLAP_TOKENS_TOPIC_ONLY
        if overlap_tokens:
            reasons.append(f"تقاطع كلمات محددة مع نوايا البحث (لا يوجد كتالوج مباشر): {'، '.join(sorted(overlap_tokens)[:5])}")

    category_overlap_score = min(1.0, len(overlap_tokens) / max(min_overlap_required, 1))

    intent_overlap_score = min(1.0, shared_intent_count / 3)
    if shared_intent_count:
        reasons.append(f"ظهر عبر {shared_intent_count} نية بحث مختلفة")

    relevance_score = round(0.6 * category_overlap_score + 0.4 * intent_overlap_score, 3)
    is_eligible = (
        shared_intent_count >= MIN_SHARED_INTENTS_FOR_DIRECT
        and len(overlap_tokens) >= min_overlap_required
        and relevance_score >= DIRECT_RELEVANCE_THRESHOLD
    )
    if is_eligible:
        confidence = DIRECT_CONFIDENCE
    elif relevance_score > 0 or shared_intent_count >= MIN_SHARED_INTENTS_FOR_DIRECT:
        confidence = RETAILER_CONFIDENCE
    else:
        confidence = UNKNOWN_CONFIDENCE

    return RelevanceAssessment(
        relevance_score=relevance_score, reasons=reasons, classification_confidence=confidence,
        is_eligible_for_direct=is_eligible,
    )


def _evidence_ids_for_stable_intents(session: Session, store_id: uuid.UUID, stable_intent_ids: list[str]) -> list[str]:
    if not stable_intent_ids:
        return []
    stable_uuids = [uuid.UUID(s) for s in stable_intent_ids]
    serp_ids = session.exec(
        select(SerpObservation.id)
        .where(SerpObservation.store_id == store_id)
        .where(SerpObservation.stable_intent_id.in_(stable_uuids))  # type: ignore[attr-defined]
    ).all()
    ai_ids = session.exec(
        select(AIVisibilityObservation.id)
        .where(AIVisibilityObservation.store_id == store_id)
        .where(AIVisibilityObservation.stable_intent_id.in_(stable_uuids))  # type: ignore[attr-defined]
    ).all()
    if not serp_ids and not ai_ids:
        return []
    evidence = session.exec(
        select(Evidence.id).where(
            Evidence.store_id == store_id,
            or_(
                and_(Evidence.source_type == EvidenceSourceType.serp_observation, Evidence.source_id.in_(serp_ids)),  # type: ignore[attr-defined]
                and_(
                    Evidence.source_type == EvidenceSourceType.ai_visibility_observation,
                    Evidence.source_id.in_(ai_ids),  # type: ignore[attr-defined]
                ),
            ),
        )
    ).all()
    return [str(e) for e in evidence]


def classify_competitors_for_run(session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID) -> int:
    """Part G-B2 — runs once per research run, immediately after competitor
    discovery mines this run's relationships (no new task, no new AI/search
    call). Every Competitor row touched this run gets reclassified, so
    classification improves as more shared-intent evidence accumulates
    across runs instead of staying frozen at first-seen time.

    'Business competitor' vs 'visibility entity' is a query-time read of
    `classification` (only direct_competitor counts as a primary business
    competitor) — nothing is ever deleted, YouTube/Amazon/gov sites stay in
    the data as visibility-relevant entities, just correctly labeled.
    """
    categories = session.exec(select(Category).where(Category.store_id == store_id)).all()
    products = session.exec(select(Product).where(Product.store_id == store_id)).all()
    real_catalog_tokens: set[str] = set()
    for category in categories:
        real_catalog_tokens |= _content_tokens(category.name or "")
    for product in products:
        real_catalog_tokens |= _content_tokens(product.name or "")

    # Part G-B6 live-benchmark finding: Category/Product names are empty for
    # several real Salla/Zid-style stores (a pre-existing crawler-extraction
    # gap, not something this function can fix) and, even when present, are
    # frequently in a different language than the market's SERP titles (an
    # English catalog like Allbirds' vs. Arabic google.sa result titles) —
    # either way real_catalog_tokens ends up unable to ever intersect
    # anything, so direct_competitor never fired on any of the 5 live
    # benchmark stores. Intent.topic is a much more robust overlap signal:
    # it always exists (AI-expanded intents don't depend on catalog
    # extraction succeeding) and is generated in the store's actual
    # target_language (Part B fix). Part R2-F3 — kept in its OWN set, never
    # merged into real_catalog_tokens: a SERP result answering a query
    # tends to echo that query's own words back regardless of what it
    # actually sells, so this is a weaker, self-referential-prone signal
    # (see assess_vertical_relevance) that only substitutes for a real
    # catalog, never strengthens one that already exists.
    intents = session.exec(
        select(Intent).where(Intent.research_run_id == research_run_id).where(Intent.is_accepted == True)  # noqa: E712
    ).all()
    intent_topic_tokens: set[str] = set()
    for intent in intents:
        intent_topic_tokens |= _content_tokens(intent.topic or "")

    relationships = session.exec(
        select(CompetitorRelationship).where(CompetitorRelationship.research_run_id == research_run_id)
    ).all()
    by_competitor: dict[uuid.UUID, list[CompetitorRelationship]] = defaultdict(list)
    for relationship in relationships:
        by_competitor[relationship.competitor_id].append(relationship)

    # SERP result titles this run, aggregated per domain — a much richer
    # catalog-overlap signal than the bare domain string (Arabic content
    # words show up in titles, rarely in a Latin-script domain name).
    serp_observations = session.exec(
        select(SerpObservation).where(SerpObservation.research_run_id == research_run_id)
    ).all()
    titles_by_domain: dict[str, list[str]] = defaultdict(list)
    for observation in serp_observations:
        for result in observation.results:
            domain = result.get("domain")
            title = result.get("title")
            if domain and title:
                titles_by_domain[normalize_hostname(domain)].append(title)

    updated = 0
    for competitor_id, rels in by_competitor.items():
        competitor = session.get(Competitor, competitor_id)
        if competitor is None:
            continue

        shared_stable_intents = sorted({str(r.stable_intent_id) for r in rels if r.stable_intent_id})
        shared_count = len(shared_stable_intents)
        known = classify_known_domain(competitor.domain)

        if known is not None:
            classification, confidence, reason = known
            relevance_score = 0.0  # known non-competitor categories never rank as a business competitor
        else:
            domain_tokens = _content_tokens(competitor.domain)
            title_tokens: set[str] = set()
            for title in titles_by_domain.get(competitor.domain, []):
                title_tokens |= _content_tokens(title)

            # Part R2-F3 — Candidate Domain -> Domain Classification (above)
            # -> Vertical Relevance (here) -> Competitor Eligibility ->
            # Direct Competitor. A domain is never promoted to
            # direct_competitor on co-occurrence alone; it needs positive,
            # *specific* evidence of a real commercial intersection.
            assessment = assess_vertical_relevance(
                domain_tokens=domain_tokens, title_tokens=title_tokens,
                real_catalog_tokens=real_catalog_tokens, intent_topic_tokens=intent_topic_tokens,
                shared_intent_count=shared_count,
            )
            relevance_score = assessment.relevance_score
            confidence = assessment.classification_confidence

            if assessment.is_eligible_for_direct:
                classification = "direct_competitor"
                reason = "؛ ".join(assessment.reasons)
            elif shared_count >= MIN_SHARED_INTENTS_FOR_DIRECT:
                classification = "retailer"
                reason = (
                    "؛ ".join(assessment.reasons)
                    if assessment.reasons
                    else f"ظهر عبر {shared_count} نية بحث مختلفة لكن دون تقاطع محدد كافٍ مع كتالوج المتجر"
                )
            else:
                classification = "unknown"
                reason = "ظهر لنية بحث واحدة فقط — بيانات غير كافية للتصنيف بثقة"

        competitor.classification = classification
        competitor.classification_confidence = confidence
        competitor.discovery_reason = reason
        competitor.relevance_score = relevance_score
        competitor.shared_stable_intents = shared_stable_intents
        competitor.evidence_ids = _evidence_ids_for_stable_intents(session, store_id, shared_stable_intents)
        session.add(competitor)
        updated += 1

    session.commit()
    return updated


def is_business_competitor(competitor: Competitor) -> bool:
    """The one predicate the product should ever use to decide 'show this
    as a competitor to the store owner' — never Competitor.competitor_type
    (that's discovery mechanism, not business relevance)."""
    return competitor.classification == "direct_competitor"
