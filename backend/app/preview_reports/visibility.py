"""Stage 6+7 (spec) — deterministic brand-appearance detection and
visibility scoring for a PreviewReport. No LLM involved: whether the
brand appeared is decided entirely by domain matching (registered_domain,
same as app.ai_visibility.multi_engine_runner.
build_deterministic_search_analysis) and light Arabic/English text
normalization — never by asking a model to judge its own or another
model's answer.

Core principle (spec, verbatim): "Unknown أفضل من Wrong". A query whose
source failed technically never becomes a false 'not found' — its
brand_found stays None and it is excluded from the visibility
denominator entirely (see compute_visibility_scores). A query whose
source succeeded but whose result is too ambiguous to judge (e.g. an
empty AI answer) also gets brand_found=None, but — being a technically
successful search — still counts in the denominator, per the spec's
exact formula: visibility = brand_appeared / successful_searches, where
"successful" means the operation succeeded, not that detection was
unambiguous."""

import re
from urllib.parse import urlparse

from app.core.domain import registered_domain
from app.core.urls import normalize_hostname

_DIACRITICS_AND_TATWEEL = re.compile(r"[ؗ-ًؚ-ْٰـ]")
_ALEF_VARIANTS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})


def normalize_brand_text(text: str) -> str:
    """Lowercase (Latin) + strip Arabic diacritics/tatweel + unify alef
    variants + unify ya/alef-maksura and ta-marbuta/ha — enough to match
    'ظُهور' against 'ظهور' or 'المتجر' against 'متجر' without a full NLP
    stemmer, which this deliberately isn't (a stemmer risks false
    positives; this only collapses cosmetic spelling variants)."""
    normalized = text.strip().lower()
    normalized = _DIACRITICS_AND_TATWEEL.sub("", normalized)
    normalized = normalized.translate(_ALEF_VARIANTS)
    normalized = normalized.replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", normalized).strip()


def build_brand_candidates(*, brand_name: str, domain: str, aliases: list[str] | None = None) -> list[str]:
    """Every safe string the deterministic text-matcher is allowed to
    treat as 'this store', normalized and deduped. domain is included
    because a raw AI answer sometimes names the site by its domain rather
    than its brand (e.g. 'يمكنك زيارة example.com')."""
    raw = {brand_name, domain, *(aliases or [])}
    seen: set[str] = set()
    candidates: list[str] = []
    for value in raw:
        if not value or not value.strip():
            continue
        normalized = normalize_brand_text(value)
        if normalized and len(normalized) >= 2 and normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)
    return candidates


def _detect_domain_match(url_or_domain: str, store_domain: str) -> bool:
    hostname = urlparse(url_or_domain).hostname or url_or_domain
    hostname = normalize_hostname(hostname)
    if not hostname:
        return False
    return registered_domain(hostname) == registered_domain(normalize_hostname(store_domain))


def analyze_google_result(google: dict, *, store_domain: str) -> dict:
    """google: the raw dict from app.preview_reports.search's Google leg
    ({"status", "results": [{"rank","domain","url","title"}]} or
    {"status": "failed"}). A Google organic rank IS the mention rank — no
    separate lookup needed, same as build_deterministic_search_analysis."""
    if google.get("status") != "success":
        return {**google, "brand_found": None, "position": None}

    position = None
    for item in google.get("results", []):
        candidate_url = item.get("url") or item.get("domain") or ""
        if candidate_url and _detect_domain_match(candidate_url, store_domain):
            position = item.get("rank")
            break
    return {**google, "brand_found": position is not None, "position": position}


def analyze_ai_result(ai: dict, *, brand_candidates: list[str], store_domain: str) -> dict:
    """ai: the raw dict from app.preview_reports.search's AI leg
    ({"status", "raw_result": str, "sources": [{"url": ...}, ...]} or
    {"status": "failed"}). 'position' here is the source's citation
    order (1-indexed) among the engine's own sources[], the closest
    analog to a Google rank an AI prose answer has — None when the brand
    was only found in free text with no matching citation."""
    if ai.get("status") != "success":
        return {**ai, "brand_found": None, "position": None}

    raw_text = ai.get("raw_result") or ""
    sources = ai.get("sources") or []

    if not raw_text.strip() and not sources:
        # Technically successful, but nothing to actually judge — unknown,
        # never guessed as not-found.
        return {**ai, "brand_found": None, "position": None}

    position = None
    for index, source in enumerate(sources, start=1):
        url = source.get("url") if isinstance(source, dict) else None
        if url and _detect_domain_match(url, store_domain):
            position = index
            break

    found_in_text = any(candidate in normalize_brand_text(raw_text) for candidate in brand_candidates)
    brand_found = found_in_text or position is not None
    return {**ai, "brand_found": brand_found, "position": position}


def enrich_query_results(
    query_results: list[dict], *, brand_name: str, domain: str, aliases: list[str] | None = None
) -> list[dict]:
    """query_results: the list from app.preview_reports.search.
    run_preview_searches(). Returns the same list with each query's
    "google"/"ai" dicts extended with brand_found/position, leaving
    status/raw fields untouched."""
    brand_candidates = build_brand_candidates(brand_name=brand_name, domain=domain, aliases=aliases)
    enriched: list[dict] = []
    for query in query_results:
        enriched.append({
            **query,
            "google": analyze_google_result(query["google"], store_domain=domain),
            "ai": analyze_ai_result(query["ai"], brand_candidates=brand_candidates, store_domain=domain),
        })
    return enriched


def _score_for_source(enriched_queries: list[dict], source: str) -> dict:
    successful = [q[source] for q in enriched_queries if q[source].get("status") == "success"]
    denom = len(successful)
    appeared = sum(1 for r in successful if r.get("brand_found") is True)
    percentage = round((appeared / denom) * 100) if denom else None
    return {"appeared": appeared, "successful_searches": denom, "percentage": percentage}


def _query_level_score(enriched_queries: list[dict]) -> dict:
    """A query counts as 'successful' if at least one of its two legs
    (google/ai) actually completed, and 'appeared' if the store was found
    on either leg — this is the per-query denominator the UI's headline
    copy narrates ("ظهر متجرك في 8 من 30 عملية بحث فحصناها"), distinct from
    the per-source breakdown in _score_for_source (out of 30 each)."""
    appeared = 0
    successful = 0
    for query in enriched_queries:
        google = query.get("google") or {}
        ai = query.get("ai") or {}
        if google.get("status") != "success" and ai.get("status") != "success":
            continue
        successful += 1
        if google.get("brand_found") is True or ai.get("brand_found") is True:
            appeared += 1
    percentage = round((appeared / successful) * 100) if successful else None
    return {"appeared": appeared, "successful": successful, "percentage": percentage}


def compute_visibility_scores(enriched_queries: list[dict]) -> dict:
    """Stage 7 formula: visibility = brand_appeared / successful × 100.
    `overall`/`overall_details` are query-level (denominator = queries with
    at least one successful leg, capped at 30) — the number the headline
    score and "measured vs estimated" sample-size gate are both based on.
    `google`/`ai` stay per-source (denominator = that source's own
    successful searches) for the Google/AI breakdown cards. Failed
    searches are excluded from every denominator, never counted as
    non-appearances."""
    google_score = _score_for_source(enriched_queries, "google")
    ai_score = _score_for_source(enriched_queries, "ai")
    overall_details = _query_level_score(enriched_queries)
    return {
        "overall": overall_details["percentage"],
        "overall_details": {"appeared": overall_details["appeared"], "successful": overall_details["successful"]},
        "google": google_score["percentage"],
        "ai": ai_score["percentage"],
        "details": {"google": google_score, "ai": ai_score},
    }


MIN_SUCCESSFUL_QUERIES_FOR_MEASURED = 10


def _has_confirmed_gap(enriched_queries: list[dict]) -> bool:
    """A genuine, successfully-checked non-appearance on either leg — the
    same evidence bar app.preview_reports.recommendation.
    build_missing_query_evidence uses, duplicated here (rather than
    imported) to keep this module free of a recommendation-domain
    dependency."""
    for query in enriched_queries:
        google = query.get("google") or {}
        ai = query.get("ai") or {}
        if google.get("status") == "success" and google.get("brand_found") is False:
            return True
        if ai.get("status") == "success" and ai.get("brand_found") is False:
            return True
    return False


def classify_visibility(scores: dict, enriched_queries: list[dict], competitors: list[dict]) -> dict:
    """Stage 7b (spec) — measured vs estimated. 'measured' requires a
    combined successful-query sample large enough to trust an exact
    percentage (MIN_SUCCESSFUL_QUERIES_FOR_MEASURED). Below that, this
    degrades to 'estimated', which — per the spec's explicit rule — "can
    identify weakness/risk" (a confirmed brand_found=False, or a thin-but-
    real score under 50%) but "cannot certify strong visibility": with no
    strong-signal evidence, it returns level='limited' with no score and
    no range claim, never a guessed percentage or a false "ظهور ممتاز"."""
    successful = scores["overall_details"]["successful"]

    if successful >= MIN_SUCCESSFUL_QUERIES_FOR_MEASURED:
        return {
            "mode": "measured",
            "score": scores["overall"],
            "brand_mentions": scores["overall_details"]["appeared"],
            "successful_checks": successful,
            "google_score": scores["google"],
            "ai_score": scores["ai"],
        }

    if successful == 0:
        return {"mode": "estimated", "score": None, "level": "limited"}

    weak_score = scores["overall"] is not None and scores["overall"] < 50
    confirmed_gap = _has_confirmed_gap(enriched_queries)
    if not (weak_score or confirmed_gap):
        return {"mode": "estimated", "score": None, "level": "limited"}

    reasons = ["limited_brand_presence"]
    if any((c.get("appearances") or 0) > 0 for c in competitors):
        reasons.append("competitor_presence")
    if confirmed_gap:
        reasons.append("content_gap")

    return {"mode": "estimated", "score": None, "level": "low", "display_range": "under_50", "reasons": reasons}
