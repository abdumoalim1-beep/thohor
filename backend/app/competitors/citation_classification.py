"""Part 2 MVP — classifies a citation source URL (one entry from
EngineAnswer.sources[], returned by the engine's own web_search tool call —
no separate extraction step needed, unlike the original Phase 15 plan).
Reuses classify_known_domain directly rather than a second, divergent
exclusion/classification list — the same reuse the Phase 4 competitor
discovery module already relies on."""

from urllib.parse import urlparse

from app.competitors.classification import classify_known_domain
from app.core.domain import registered_domain
from app.core.urls import normalize_hostname


def classify_citation_source_type(
    url: str, *, client_hostname: str, competitor_domains: set[str] = frozenset()
) -> str:
    hostname = normalize_hostname(urlparse(url).hostname or "")
    if not hostname:
        return "unknown"

    client_registered = registered_domain(client_hostname)
    if registered_domain(hostname) == client_registered:
        return "official_store"

    competitor_registered = {registered_domain(d) for d in competitor_domains}
    if registered_domain(hostname) in competitor_registered:
        return "competitor_store"

    known = classify_known_domain(hostname)
    if known is not None:
        return known[0]  # marketplace/wholesale/social/forum/video/publisher/irrelevant/educational/government

    return "other"
