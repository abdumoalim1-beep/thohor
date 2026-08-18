"""Extended display-name fallback chain — engaged only when both existing
tiers (a real, non-guessed crawl-extracted Brand.name, and web-search
identity resolution) have already been exhausted (see
app.api.stores.get_store_understanding). Deliberately does not touch
app.store_intelligence.identity_resolver or app.crawler.store_intelligence's
classification/Brand-upsert logic — this reads already-crawled, already-
stored PageObservation data at request time; it never triggers a new crawl
or network call.

Priority order (user-specified): web search (handled by the caller before
this function is ever invoked) -> schema.org Organization/WebSite JSON-LD
-> og:site_name -> <title> -> logo image alt text -> a formatted name
derived from the domain (last resort, never fails)."""

from html import unescape
from urllib.parse import urlparse

from app.api.store_profile import _json_ld_values
from app.crawler.store_intelligence import _guess_brand_name_from_domain

NameSource = str  # "structured_data" | "og_site_name" | "page_title" | "logo_alt" | "domain_guess"

_LOGO_MARKERS = ("logo", "شعار")


def _find_logo_alt_text(images: list[dict]) -> str | None:
    """Best-effort selection of 'the logo' among every image already
    captured on the home page — no DOM-position data is stored, so this
    matches on alt text or the image URL containing a logo marker. Never a
    new network call; reads app.crawler.extract's already-crawled
    PageFacts.images list."""
    for image in images:
        if not isinstance(image, dict):
            continue
        alt = image.get("alt")
        url = image.get("url") or ""
        haystack = f"{alt or ''} {url}".lower()
        if any(marker in haystack for marker in _LOGO_MARKERS):
            if isinstance(alt, str) and alt.strip():
                return alt.strip()
    return None


def _clean_title(title: str) -> str:
    """Strips the common '<site name> | <page-specific suffix>' or
    '<site name> — <suffix>' patterns down to just the leading segment —
    the same cleanup app.api.store_profile._display_name already applies,
    kept independent here since that function is a different, unrelated
    fallback chain this module must not modify."""
    return title.split("|")[0].split("—")[0].split("-")[0].strip()


def resolve_best_available_name(*, home_extraction: dict, base_url: str) -> tuple[str, NameSource]:
    """(name, source). Only called once the caller has already exhausted a
    real Brand.name and web-search identity — this is tiers 2-6 of the
    user-specified priority order. The final tier (domain-derived) never
    fails, so this function always returns a usable name."""
    for kind in ("Organization", "WebSite"):
        for entity in _json_ld_values(home_extraction, kind):
            name = entity.get("name")
            if isinstance(name, str) and name.strip():
                return unescape(name.strip()), "structured_data"

    og_site_name = home_extraction.get("og_site_name")
    if isinstance(og_site_name, str) and og_site_name.strip():
        return unescape(og_site_name.strip()), "og_site_name"

    title = home_extraction.get("title")
    if isinstance(title, str) and title.strip():
        cleaned = _clean_title(title)
        if cleaned:
            return unescape(cleaned), "page_title"

    logo_alt = _find_logo_alt_text(home_extraction.get("images") or [])
    if logo_alt:
        return unescape(logo_alt), "logo_alt"

    return _guess_brand_name_from_domain(base_url), "domain_guess"


def registered_hostname(url: str) -> str:
    """The bare hostname (www.-stripped) for a store's own URL — used as
    one of the aliases when a user confirms/edits a resolved name."""
    return (urlparse(url).hostname or url).removeprefix("www.")
