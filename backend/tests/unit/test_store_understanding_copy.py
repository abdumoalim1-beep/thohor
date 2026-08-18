from app.api.schemas import StoreProfileProduct
from app.store_intelligence.understanding import build_business_info, build_category_previews


def test_classification_category_never_invents_product_count():
    previews = build_category_previews(
        ["مكياج العيون"], [],
        [StoreProfileProduct(name="مسكرا", url="https://shop.test/p/1", image_url="https://shop.test/p.jpg")],
        0.82,
    )
    assert previews[0].name == "مكياج العيون"
    assert previews[0].product_count is None
    assert previews[0].source == "observed_products"


def test_catalog_count_and_business_info_require_observed_evidence():
    previews = build_category_previews([], [("مكياج الوجه", "https://shop.test/c/face", 18)], [], None)
    assert previews[0].product_count == 18
    assert previews[0].confidence == 1.0
    info = build_business_info([
        ("سياسة الشحن والتوصيل", "https://shop.test/shipping"),
        ("بوكسات المكياج", "https://shop.test/boxes"),
    ])
    assert [item.kind for item in info] == ["shipping"]


def test_observed_products_create_balanced_categories_without_inventing_totals():
    products = [
        StoreProfileProduct(name="مسكرا سوداء", url="https://shop.test/p/1", image_url="eye.jpg"),
        StoreProfileProduct(name="بودرة وجه", url="https://shop.test/p/2", image_url="face.jpg"),
        StoreProfileProduct(name="ربطة شعر", url="https://shop.test/p/3", image_url="hair.jpg"),
    ]
    previews = build_category_previews([], [], products, None)
    assert [item.name for item in previews] == ["مكياج العيون", "مكياج الوجه", "إكسسوارات الشعر"]
    assert all(item.product_count is None for item in previews)
    assert len({item.image_url for item in previews}) == 3
