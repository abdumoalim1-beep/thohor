from __future__ import annotations

import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlmodel import Session, select

from app.models.catalog import Category, Page, Product


TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}


def canonical_store_url(value: str | None) -> str | None:
    """Return a stable identity for a store page without changing its meaning."""
    if not value or not value.strip():
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname.lower().removeprefix("www.")
    port = f":{parsed.port}" if parsed.port and parsed.port not in {80, 443} else ""
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
        )
    )
    return urlunsplit(("https", f"{host}{port}", path, query, ""))


def resolve_catalog_targets(
    session: Session,
    store_id: uuid.UUID,
    target_url: str | None,
    affected_products: list[str] | None = None,
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Resolve explicit page/product foreign keys from observed catalog facts."""
    wanted = canonical_store_url(target_url)
    pages = session.exec(select(Page).where(Page.store_id == store_id)).all()
    page = next((item for item in pages if canonical_store_url(item.url) == wanted), None) if wanted else None

    products = session.exec(select(Product).where(Product.store_id == store_id)).all()
    product = next((item for item in products if canonical_store_url(item.url) == wanted), None) if wanted else None
    if product is None:
        for raw_id in affected_products or []:
            try:
                candidate = session.get(Product, uuid.UUID(str(raw_id)))
            except (ValueError, TypeError):
                continue
            if candidate is not None and candidate.store_id == store_id:
                product = candidate
                break
    return (page.id if page else None, product.id if product else None)


def resolve_product_category(session: Session, product: Product, internal_links: list[str]) -> Category | None:
    """Use only category URLs actually linked from the observed product page."""
    linked = {canonical_store_url(url) for url in internal_links}
    candidates = session.exec(select(Category).where(Category.store_id == product.store_id)).all()
    matches = [category for category in candidates if category.url and canonical_store_url(category.url) in linked]
    if not matches:
        return None
    # Deeper paths are normally the most specific category in a breadcrumb/navigation trail.
    return max(matches, key=lambda category: len(urlsplit(category.url or "").path))
