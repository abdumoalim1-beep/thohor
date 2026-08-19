"""Stage 8+10 (spec) — competitor extraction for a PreviewReport, straight
from the same query results already gathered in Stage 5/6 (see
app.preview_reports.search / app.preview_reports.visibility). No separate
discovery pipeline, no AI validation call — every other domain/brand seen
in the store's own Google organic results and AI citation sources is a
candidate; filtering is exactly app.competitors.classification.
classify_known_domain (the existing curated marketplace/social/video/
publisher/etc. registry), reused unmodified rather than reimplemented.

Deliberately much lighter than app.competitors.classification's full
relevance-scoring pipeline (catalog-token overlap, direct_competitor vs
retailer vs unknown, DB-persisted CompetitorRelationship rows) — that
system exists for the ongoing /signup product and needs real evidence
before promoting a domain to "competitor". This is a one-shot preview:
frequency across the same queries (Google leg capped at
settings.preview_search_google_query_count, AI leg at the larger
settings.preview_search_ai_query_count — see app.preview_reports.search)
plus the curated exclusion list is the whole signal, per the spec's
explicit "no complex AI competitor validation needed for MVP"."""

from collections import defaultdict
from urllib.parse import urlparse

from app.competitors.classification import classify_known_domain
from app.core.domain import registered_domain
from app.core.urls import normalize_hostname

MAX_COMPETITORS = 10


def _count_successful_searches(enriched_queries: list[dict]) -> int:
    count = 0
    for query in enriched_queries:
        if (query.get("google") or {}).get("status") == "success":
            count += 1
        if (query.get("ai") or {}).get("status") == "success":
            count += 1
    return count


def extract_competitors(enriched_queries: list[dict], *, store_domain: str) -> list[dict]:
    """enriched_queries: the list from app.preview_reports.visibility.
    enrich_query_results(). Returns up to MAX_COMPETITORS competitors,
    sorted by how often they appeared, each with the same visibility %
    formula (appearances / total successful searches × 100) used for the
    store's own score — comparable numbers, same denominator discipline."""
    store_registered = registered_domain(normalize_hostname(store_domain))
    hits_by_domain: dict[str, list[dict]] = defaultdict(list)
    display_hostname: dict[str, str] = {}

    for query in enriched_queries:
        google = query.get("google") or {}
        if google.get("status") == "success":
            for item in google.get("results", []):
                hostname = normalize_hostname(item.get("domain") or "")
                if not hostname:
                    continue
                registered = registered_domain(hostname)
                if registered == store_registered or classify_known_domain(registered) is not None:
                    continue
                hits_by_domain[registered].append({"query": query["query"], "rank": item.get("rank")})
                display_hostname.setdefault(registered, hostname)

        ai = query.get("ai") or {}
        if ai.get("status") == "success":
            for source in ai.get("sources") or []:
                url = source.get("url") if isinstance(source, dict) else None
                if not url:
                    continue
                hostname = normalize_hostname(urlparse(url).hostname or "")
                if not hostname:
                    continue
                registered = registered_domain(hostname)
                if registered == store_registered or classify_known_domain(registered) is not None:
                    continue
                hits_by_domain[registered].append({"query": query["query"], "rank": None})
                display_hostname.setdefault(registered, hostname)

    total_successful = _count_successful_searches(enriched_queries)

    competitors = []
    for domain, hits in hits_by_domain.items():
        ranks = [h["rank"] for h in hits if h.get("rank")]
        appearances = len(hits)
        competitors.append({
            "domain": display_hostname[domain],
            "appearances": appearances,
            "average_rank": round(sum(ranks) / len(ranks), 1) if ranks else None,
            "visibility_percentage": round((appearances / total_successful) * 100) if total_successful else None,
            "queries": sorted({h["query"] for h in hits}),
        })

    competitors.sort(key=lambda c: c["appearances"], reverse=True)
    return competitors[:MAX_COMPETITORS]
