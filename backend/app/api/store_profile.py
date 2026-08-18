import uuid
from html import unescape
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.api.schemas import StoreProfile, StoreProfileCategory, StoreProfileProduct
from app.models.catalog import Brand, Category, Page, Product
from app.models.observation import PageObservation
from app.models.store import Store


def _valid_http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _json_ld_values(extraction: dict, kind: str) -> list[dict]:
    values: list[dict] = []
    for entry in extraction.get("json_ld") or []:
        if not isinstance(entry, dict):
            continue
        graph = entry.get("@graph")
        candidates = graph if isinstance(graph, list) else [entry]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            raw_types = candidate.get("@type")
            types = [raw_types] if isinstance(raw_types, str) else (raw_types or [])
            if kind in types:
                values.append(candidate)
    return values


def _image_url(product_data: dict) -> str | None:
    image = product_data.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")
    return _valid_http_url(image)


def _display_name(store: Store, home_extraction: dict, brands: list[Brand]) -> str:
    for kind in ("Organization", "Brand"):
        for entity in _json_ld_values(home_extraction, kind):
            name = entity.get("name")
            if isinstance(name, str) and name.strip():
                return unescape(name.strip())
    if brands:
        return unescape(brands[0].name)
    h1 = home_extraction.get("h1")
    if isinstance(h1, str) and 1 < len(h1.strip()) <= 80:
        return unescape(h1.strip())
    title = home_extraction.get("title")
    if isinstance(title, str) and title.strip():
        return unescape(title.split("|")[0].split("—")[0].strip())
    return (urlparse(store.url).hostname or store.url).removeprefix("www.").split(".")[0].title()


def build_store_profile(
    session: Session,
    store: Store,
    classification: dict | None,
) -> StoreProfile | None:
    pages = session.exec(select(Page).where(Page.store_id == store.id)).all()
    if not pages:
        return None

    products = session.exec(select(Product).where(Product.store_id == store.id)).all()
    categories = session.exec(select(Category).where(Category.store_id == store.id)).all()
    brands = session.exec(select(Brand).where(Brand.store_id == store.id)).all()
    observations = session.exec(
        select(PageObservation)
        .where(PageObservation.store_id == store.id)
        .order_by(PageObservation.observed_at.desc())  # type: ignore[arg-type]
    ).all()

    latest_by_url: dict[str, PageObservation] = {}
    for observation in observations:
        latest_by_url.setdefault(observation.source_url, observation)

    home_page = next((page for page in pages if page.page_type == "home"), None)
    home_observation = latest_by_url.get(home_page.url) if home_page else None
    home_extraction = home_observation.normalized_extraction if home_observation else {}

    page_type_counts: dict[str, int] = {}
    for page in pages:
        page_type = page.page_type or "other"
        page_type_counts[page_type] = page_type_counts.get(page_type, 0) + 1

    product_items: list[StoreProfileProduct] = []
    for product in products[:6]:
        extraction = (latest_by_url.get(product.url).normalized_extraction if latest_by_url.get(product.url) else {}) or {}
        product_data = next(iter(_json_ld_values(extraction, "Product") or _json_ld_values(extraction, "ProductGroup")), {})
        product_items.append(
            StoreProfileProduct(name=product.name, url=product.url, image_url=_image_url(product_data))
        )

    # Some storefronts expose Product JSON-LD on URLs that their route shape
    # does not classify as /product/. Keep these as preview-only facts rather
    # than inflating the canonical Product count.
    seen_product_urls = {item.url for item in product_items}
    if len(product_items) < 6:
        for source_url, observation in latest_by_url.items():
            if source_url in seen_product_urls:
                continue
            extraction = observation.normalized_extraction or {}
            product_data = next(iter(_json_ld_values(extraction, "Product") or _json_ld_values(extraction, "ProductGroup")), None)
            if not product_data:
                continue
            name = product_data.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            product_items.append(StoreProfileProduct(name=name.strip(), url=source_url, image_url=_image_url(product_data)))
            seen_product_urls.add(source_url)
            if len(product_items) == 6:
                break

    description = home_extraction.get("meta_description")
    if not isinstance(description, str) or not description.strip():
        description = None

    domain = (urlparse(store.url).hostname or store.url).removeprefix("www.")
    business_type = classification.get("business_type") if classification else None
    confidence = classification.get("confidence") if classification else None
    primary_categories = classification.get("primary_categories", []) if classification else []

    return StoreProfile(
        name=_display_name(store, home_extraction, brands),
        domain=domain,
        title=home_extraction.get("title"),
        description=description,
        country=store.country,
        language=store.language,
        locale_status=store.locale_status,
        locale_confidence=store.locale_confidence,
        platform=store.platform_hint,
        business_type=business_type if isinstance(business_type, str) else None,
        classification_confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
        primary_categories=[str(value) for value in primary_categories if value][:4],
        products_count=len(products) if products else None,
        categories_count=len(categories) if categories else None,
        brands_count=len(brands) if brands else None,
        pages_count=len(pages),
        page_type_counts=page_type_counts,
        products=product_items,
        categories=[StoreProfileCategory(name=category.name, url=category.url) for category in categories[:4]],
        brands=[brand.name for brand in brands[:5]],
    )
