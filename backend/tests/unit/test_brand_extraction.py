from sqlmodel import select

from app.crawler.store_intelligence import _ensure_fallback_brand, _extract_brand_candidates, _upsert_brand
from app.models.catalog import Brand
from app.models.org import Organization
from app.models.store import Store


def _make_store(session):
    org = Organization(name="t", slug="t-brand")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://roastinghouse.sa")
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


def test_extract_brand_candidates_from_organization_schema():
    json_ld = [{"@type": "Organization", "name": "Roasting House"}]
    assert _extract_brand_candidates(json_ld) == ["Roasting House"]


def test_extract_brand_candidates_from_product_brand():
    json_ld = [{"@type": "Product", "name": "x", "brand": {"@type": "Brand", "name": "Allbirds"}}]
    assert _extract_brand_candidates(json_ld) == ["Allbirds"]


def test_extract_brand_candidates_from_product_brand_as_string():
    json_ld = [{"@type": "Product", "name": "x", "brand": "Allbirds"}]
    assert _extract_brand_candidates(json_ld) == ["Allbirds"]


def test_extract_brand_candidates_ignores_unrelated_types():
    json_ld = [{"@type": "BreadcrumbList", "name": "not a brand"}]
    assert _extract_brand_candidates(json_ld) == []


def test_upsert_brand_creates_one_row_and_merges_aliases_on_repeat(session):
    store = _make_store(session)

    first = _upsert_brand(session, store.id, "Roasting House", store.url)
    second = _upsert_brand(session, store.id, "روستنج هاوس", store.url)

    assert first.id == second.id  # one brand per store in V1

    brands = session.exec(select(Brand).where(Brand.store_id == store.id)).all()
    assert len(brands) == 1
    assert "روستنج هاوس" in brands[0].aliases


def test_ensure_fallback_brand_only_when_no_brand_exists(session):
    store = _make_store(session)

    _ensure_fallback_brand(session, store.id, "https://roastinghouse.sa")

    brands = session.exec(select(Brand).where(Brand.store_id == store.id)).all()
    assert len(brands) == 1
    assert brands[0].name == "Roastinghouse"


def test_ensure_fallback_brand_does_not_override_existing_brand(session):
    store = _make_store(session)
    _upsert_brand(session, store.id, "Real Brand Name", store.url)

    _ensure_fallback_brand(session, store.id, "https://roastinghouse.sa")

    brands = session.exec(select(Brand).where(Brand.store_id == store.id)).all()
    assert len(brands) == 1
    assert brands[0].name == "Real Brand Name"
