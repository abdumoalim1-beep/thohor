"""Part R3.1 (Round 1 remediation) — public-suffix-aware domain
normalization. Deliberately not `hostname.split(".")[-2:]` or a bare
`www.`-strip: those break on multi-part public suffixes (.com.sa, .co.uk,
.gov.sa, ...), which is exactly why `app.competitors.classification`'s old
curated-domain check missed `ar.wikipedia.org` (only `wikipedia.org` was
in the denylist, and only a `www.` prefix was ever stripped before the
lookup)."""

from dataclasses import dataclass

import tldextract

# suffix_list_urls=() — never fetch the public suffix list over the
# network; use only the snapshot bundled with the package. Deterministic,
# offline, safe for tests and for the "zero live calls" discipline this
# whole remediation phase runs under (this isn't a SerpAPI/OpenAI call,
# but there's no reason for a domain-parsing utility to ever touch the
# network at all).
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


@dataclass(frozen=True)
class DomainParts:
    subdomain: str  # "" if none, e.g. "ar" for ar.wikipedia.org
    domain: str  # e.g. "wikipedia"
    suffix: str  # e.g. "org", or "com.sa" (multi-part suffixes handled correctly)
    registered_domain: str  # e.g. "wikipedia.org" — domain + suffix, no subdomain


def parse_domain(hostname: str) -> DomainParts:
    result = _extract(hostname.strip().lower())
    registered = f"{result.domain}.{result.suffix}" if result.suffix else result.domain
    return DomainParts(
        subdomain=result.subdomain,
        domain=result.domain,
        suffix=result.suffix,
        registered_domain=registered,
    )


def registered_domain(hostname: str) -> str:
    """The one thing most callers actually want: the registrable domain
    with any subdomain (www., ar., m., shop., ...) stripped, suffix-aware.
    `ar.wikipedia.org` and `en.wikipedia.org` and `www.wikipedia.org` and
    `wikipedia.org` all resolve to the same `wikipedia.org`."""
    return parse_domain(hostname).registered_domain


# Part R7 (Round 1 remediation) — RFC 2606 reserved domains: names set aside
# specifically for documentation/testing that can never resolve to a real
# business. MockSearchProvider's deterministic fixture output
# ("example-competitor-N.test") lives under one of these; this check is
# intentionally broader than that one literal pattern so it also catches any
# other synthetic/example domain a future fixture might introduce.
_RESERVED_TEST_SUFFIXES = (".test", ".example", ".invalid", ".localhost")
_RESERVED_TEST_REGISTERED_DOMAINS = {"example.com", "example.org", "example.net"}


def is_synthetic_test_domain(hostname: str) -> bool:
    """True for RFC 2606 reserved test domains. Traced root cause (Part R7):
    a discarded dry-run research run replayed (via ReplaySearchProvider) an
    old serp_observations row that had itself been produced by
    MockSearchProvider during earlier dev/benchmark testing against the
    same persistent database — ReplaySearchProvider has no way to know the
    historical data it serves was ever synthetic, and the discovery engine
    mined it into real-looking Competitor rows (some even classified
    direct_competitor). This is the guard that stops that class of
    contamination at the one place it actually matters — where a domain is
    about to become a persisted Competitor — regardless of which upstream
    code path produced it or whether a mode/provider-identity signal was
    available at the time."""
    normalized = hostname.strip().lower()
    if any(normalized.endswith(suffix) for suffix in _RESERVED_TEST_SUFFIXES):
        return True
    return registered_domain(normalized) in _RESERVED_TEST_REGISTERED_DOMAINS


def matches_curated_domain(hostname: str, curated_domain: str) -> bool:
    """True when `hostname` is `curated_domain` or any subdomain of it —
    the suffix-aware replacement for the old
    `bare in FROZEN_SET_OF_BARE_DOMAINS` exact-match check, which could
    never match a subdomain like ar.wikipedia.org against a curated
    "wikipedia.org" entry.

    Most curated entries are bare registrable domains ("wikipedia.org",
    "facebook.com") — any subdomain of the input matches those. A few
    (e.g. "apps.apple.com", one specific subdomain of the much bigger,
    otherwise-unrelated apple.com) are themselves subdomain-specific; for
    those, only that exact hostname matches — apple.com itself, or some
    unrelated subdomain of it, must not."""
    curated_parts = parse_domain(curated_domain)
    host_parts = parse_domain(hostname)
    if curated_parts.subdomain:
        return host_parts.registered_domain == curated_parts.registered_domain and host_parts.subdomain == curated_parts.subdomain
    return host_parts.registered_domain == curated_parts.registered_domain
