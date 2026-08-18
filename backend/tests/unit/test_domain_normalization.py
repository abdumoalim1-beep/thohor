"""Part R3.1 — public-suffix-aware domain normalization. All offline (the
extractor is configured with suffix_list_urls=() — no network fetch)."""

from app.core.domain import is_synthetic_test_domain, matches_curated_domain, parse_domain, registered_domain


def test_parses_simple_domain():
    parts = parse_domain("krabet.sa")
    assert parts.subdomain == ""
    assert parts.domain == "krabet"
    assert parts.suffix == "sa"
    assert parts.registered_domain == "krabet.sa"


def test_parses_regional_subdomain():
    parts = parse_domain("ar.wikipedia.org")
    assert parts.subdomain == "ar"
    assert parts.registered_domain == "wikipedia.org"


def test_parses_www_subdomain():
    parts = parse_domain("www.wikipedia.org")
    assert parts.subdomain == "www"
    assert parts.registered_domain == "wikipedia.org"


def test_handles_multi_part_public_suffix_com_sa():
    """The exact failure mode of split('.')[-2:]: it would return
    'com.sa' as the 'domain', not the real registrable name."""
    parts = parse_domain("shop.example.com.sa")
    assert parts.subdomain == "shop"
    assert parts.domain == "example"
    assert parts.suffix == "com.sa"
    assert parts.registered_domain == "example.com.sa"


def test_handles_multi_part_public_suffix_co_uk():
    parts = parse_domain("www.example.co.uk")
    assert parts.registered_domain == "example.co.uk"


def test_registered_domain_is_stable_across_subdomains():
    assert registered_domain("ar.wikipedia.org") == registered_domain("en.wikipedia.org") == registered_domain("www.wikipedia.org") == registered_domain("wikipedia.org")


def test_matches_curated_domain_across_subdomains():
    assert matches_curated_domain("ar.wikipedia.org", "wikipedia.org") is True
    assert matches_curated_domain("en.wikipedia.org", "wikipedia.org") is True
    assert matches_curated_domain("www.wikipedia.org", "wikipedia.org") is True
    assert matches_curated_domain("wikipedia.org", "wikipedia.org") is True


def test_matches_curated_domain_rejects_unrelated_domains():
    assert matches_curated_domain("notwikipedia.org", "wikipedia.org") is False
    assert matches_curated_domain("wikipedia.org.evil.test", "wikipedia.org") is False
    assert matches_curated_domain("wikipediaorg.com", "wikipedia.org") is False


# Part R7 — synthetic/reserved test-domain detection. Traced root cause: a
# discarded dry-run research run replayed old serp_observations that had
# themselves been produced by MockSearchProvider during earlier dev testing
# against the same persistent database, and the discovery engine mined the
# synthetic "example-competitor-N.test" domains into real-looking Competitor
# rows. This guard is what stops that class of contamination.
def test_is_synthetic_test_domain_catches_mock_provider_pattern():
    assert is_synthetic_test_domain("example-competitor-1.test") is True
    assert is_synthetic_test_domain("example-competitor-10.test") is True


def test_is_synthetic_test_domain_catches_all_rfc2606_reserved_suffixes():
    assert is_synthetic_test_domain("anything.test") is True
    assert is_synthetic_test_domain("anything.example") is True
    assert is_synthetic_test_domain("anything.invalid") is True
    assert is_synthetic_test_domain("anything.localhost") is True
    assert is_synthetic_test_domain("sub.deep.rival.test") is True


def test_is_synthetic_test_domain_catches_reserved_example_registered_domains():
    assert is_synthetic_test_domain("example.com") is True
    assert is_synthetic_test_domain("www.example.com") is True
    assert is_synthetic_test_domain("example.org") is True
    assert is_synthetic_test_domain("example.net") is True


def test_is_synthetic_test_domain_rejects_real_looking_domains():
    assert is_synthetic_test_domain("roastinghouse.sa") is False
    assert is_synthetic_test_domain("wikipedia.org") is False
    assert is_synthetic_test_domain("rival-coffee.co") is False
    # "example" as a substring elsewhere must not false-positive.
    assert is_synthetic_test_domain("bestexample.com") is False
    assert is_synthetic_test_domain("example-shop.sa") is False
