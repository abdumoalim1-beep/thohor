import uuid

from app.models.catalog import Category, Page, Product
from app.models.org import Organization
from app.models.store import Store
from app.store_intelligence.catalog_resolution import (
    canonical_store_url,
    resolve_catalog_targets,
    resolve_product_category,
)


def _store(session) -> Store:
    organization = Organization(name="Catalog Test", slug=f"catalog-{uuid.uuid4()}")
    session.add(organization)
    session.commit()
    session.refresh(organization)
    store = Store(organization_id=organization.id, url="https://example.com")
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


def test_canonical_store_url_removes_only_tracking_noise():
    assert canonical_store_url("http://WWW.Example.com/products/item/?utm_source=x&variant=7#buy") == (
        "https://example.com/products/item?variant=7"
    )


def test_resolve_catalog_targets_links_observed_product_and_page(session):
    store = _store(session)
    page = Page(store_id=store.id, url="https://example.com/products/item", page_type="product")
    product = Product(store_id=store.id, name="Item", url="https://www.example.com/products/item/")
    session.add(page)
    session.add(product)
    session.commit()
    session.refresh(page)
    session.refresh(product)

    page_id, product_id = resolve_catalog_targets(
        session, store.id, "http://example.com/products/item?utm_campaign=test"
    )

    assert page_id == page.id
    assert product_id == product.id


def test_category_resolution_requires_an_observed_link(session):
    store = _store(session)
    broad = Category(store_id=store.id, name="All", url="https://example.com/collections/all")
    specific = Category(store_id=store.id, name="Eyes", url="https://example.com/collections/makeup/eyes")
    product = Product(store_id=store.id, name="Mascara", url="https://example.com/products/mascara")
    session.add(broad)
    session.add(specific)
    session.add(product)
    session.commit()

    assert resolve_product_category(session, product, [specific.url]) == specific
    assert resolve_product_category(session, product, ["https://example.com/pages/about"]) is None


def test_affected_product_id_is_used_when_target_is_not_a_product(session):
    store = _store(session)
    product = Product(store_id=store.id, name="Mascara", url="https://example.com/products/mascara")
    session.add(product)
    session.commit()
    session.refresh(product)

    _, product_id = resolve_catalog_targets(
        session, store.id, "https://example.com/blog/post", [str(product.id), str(uuid.uuid4())]
    )
    assert product_id == product.id
