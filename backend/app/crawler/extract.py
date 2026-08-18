import hashlib
import json
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def _valid_http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _extract_image_url(entry: dict) -> str | None:
    """schema.org `image` may be a string, a list of strings/objects, or a
    single ImageObject — never a guessed/generated image, only what the
    page's own structured data actually declares."""
    image = entry.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")
    return _valid_http_url(image)

EXTRACTOR_VERSION = "v2"


@dataclass
class PageFacts:
    """Deterministic, programmatic extraction only — no AI involved. This is
    the 'fact' half of the architecture principle (PRD section 71): the LLM
    classifies/enriches on top of this, never replaces it.
    """

    url: str
    title: str | None = None
    h1: str | None = None
    h2: list[str] = field(default_factory=list)
    meta_description: str | None = None
    og_site_name: str | None = None
    canonical: str | None = None
    hreflang: dict[str, str] = field(default_factory=dict)
    json_ld: list[dict] = field(default_factory=list)
    internal_links: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    faq_items: list[dict] = field(default_factory=list)
    html_hash: str = ""
    content_hash: str = ""
    # Part R2-F1 (Round 2 remediation) — the <html lang="..."> attribute
    # and the page's own visible body text, kept alongside the existing
    # deterministic facts so app.crawler.locale_detection can use them as
    # two more independent locale signals without a second HTML parse.
    html_lang: str | None = None
    body_text: str = ""

    def to_normalized_dict(self) -> dict:
        return {
            "title": self.title,
            "h1": self.h1,
            "h2": self.h2,
            "meta_description": self.meta_description,
            "og_site_name": self.og_site_name,
            "canonical": self.canonical,
            "hreflang": self.hreflang,
            "json_ld": self.json_ld,
            "internal_links": self.internal_links,
            "images": self.images,
            "faq_items": self.faq_items,
            "html_hash": self.html_hash,
            "content_hash": self.content_hash,
            "html_lang": self.html_lang,
        }


def extract_page_facts(url: str, html: str, site_hostname: str | None) -> PageFacts:
    soup = BeautifulSoup(html, "lxml")

    html_tag = soup.find("html")
    html_lang = html_tag.get("lang") if html_tag else None

    title = soup.title.get_text(strip=True) if soup.title else None

    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(strip=True) if h1_tag else None
    h2 = [tag.get_text(" ", strip=True) for tag in soup.find_all("h2") if tag.get_text(" ", strip=True)][:24]

    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_desc_tag.get("content", "").strip() if meta_desc_tag else None

    og_site_name_tag = soup.find("meta", attrs={"property": "og:site_name"})
    og_site_name = og_site_name_tag.get("content", "").strip() if og_site_name_tag else None

    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical = canonical_tag.get("href") if canonical_tag else None

    hreflang: dict[str, str] = {}
    for link in soup.find_all("link", attrs={"rel": "alternate"}):
        lang = link.get("hreflang")
        href = link.get("href")
        if lang and href:
            hreflang[lang] = href

    json_ld: list[dict] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        if isinstance(data, list):
            json_ld.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            json_ld.append(data)

    internal_links: set[str] = set()
    if site_hostname:
        for a in soup.find_all("a", href=True):
            absolute = urljoin(url, a["href"])
            if urlparse(absolute).hostname == site_hostname:
                internal_links.add(absolute.split("#")[0])

    images: list[dict] = []
    seen_images: set[str] = set()
    for image in soup.find_all("img"):
        raw_src = image.get("src") or image.get("data-src") or image.get("data-lazy-src")
        if not isinstance(raw_src, str):
            continue
        src = urljoin(url, raw_src)
        if not _valid_http_url(src) or src in seen_images:
            continue
        seen_images.add(src)
        images.append({
            "url": src,
            "alt": (image.get("alt") or "").strip(),
            "width": _positive_int(image.get("width")),
            "height": _positive_int(image.get("height")),
        })
        if len(images) >= 32:
            break

    faq_items: list[dict] = []
    for entry in json_ld:
        raw_type = entry.get("@type")
        types = [raw_type] if isinstance(raw_type, str) else raw_type or []
        if "FAQPage" not in types:
            continue
        for item in entry.get("mainEntity") or []:
            if not isinstance(item, dict):
                continue
            answer = item.get("acceptedAnswer") or {}
            faq_items.append({"question": item.get("name"), "answer": answer.get("text") if isinstance(answer, dict) else None})

    body_text = soup.get_text(" ", strip=True)

    return PageFacts(
        url=url,
        title=title,
        h1=h1,
        h2=h2,
        meta_description=meta_description,
        og_site_name=og_site_name,
        canonical=canonical,
        hreflang=hreflang,
        json_ld=json_ld,
        internal_links=sorted(internal_links),
        images=images,
        faq_items=faq_items[:20],
        html_hash=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        content_hash=hashlib.sha256(body_text.encode("utf-8")).hexdigest(),
        html_lang=html_lang,
        body_text=body_text[:4000],
    )


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _extract_rating(entry: dict) -> tuple[float | None, int | None]:
    """schema.org AggregateRating — both fields only ever come from this
    one real structured block, never estimated from anything else."""
    rating = entry.get("aggregateRating")
    if not isinstance(rating, dict):
        return None, None
    value = rating.get("ratingValue")
    count = rating.get("reviewCount") or rating.get("ratingCount")
    try:
        rating_value = float(value) if value is not None else None
    except (TypeError, ValueError):
        rating_value = None
    try:
        review_count = int(count) if count is not None else None
    except (TypeError, ValueError):
        review_count = None
    return rating_value, review_count


def extract_product_facts(json_ld: list[dict]) -> dict | None:
    """Pulls name/price/currency/availability/sku/rating from schema.org
    Product JSON-LD only — this is a programmatic fact, never inferred by
    AI.

    Accepts both schema.org Product and ProductGroup (used by variant-based
    catalogs, e.g. Shopify's newer JSON-LD for products with size/color
    options) — both carry a top-level `offers` in the same shape."""
    for entry in json_ld:
        raw_types = entry.get("@type")
        types = [raw_types] if isinstance(raw_types, str) else (raw_types or [])
        if "Product" not in types and "ProductGroup" not in types:
            continue

        offers = entry.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}

        rating_value, review_count = _extract_rating(entry)

        return {
            "name": entry.get("name"),
            "price": offers.get("price"),
            # No single standard schema.org field for "was" price — the
            # only reasonably common structured signal is AggregateOffer's
            # highPrice next to the current (low) price. Best-effort only:
            # None whenever the page doesn't emit this, never guessed from
            # rendered strikethrough text (that would need HTML heuristics,
            # not structured data — out of scope for a "programmatic fact").
            "original_price": offers.get("highPrice"),
            "currency": offers.get("priceCurrency"),
            "availability": offers.get("availability"),
            "sku": entry.get("sku") or entry.get("mpn"),
            "rating": rating_value,
            "review_count": review_count,
            "image_url": _extract_image_url(entry),
        }
    return None


def looks_like_category_page(json_ld: list[dict]) -> bool:
    """Symmetric to extract_product_facts' override of URL-based page-type
    classification: schema.org CollectionPage/ItemList/OfferCatalog JSON-LD
    is as strong a category signal as Product JSON-LD is for products, but
    classify_page_type() in crawl.py only ever matched on URL path segments
    for categories — fragile on site builders (Salla/Zid included) whose
    category URLs don't happen to contain /category/, /collections/, etc."""
    for entry in json_ld:
        raw_types = entry.get("@type")
        types = [raw_types] if isinstance(raw_types, str) else (raw_types or [])
        if any(t in ("CollectionPage", "ItemList", "OfferCatalog") for t in types):
            return True
    return False
