from app.store_intelligence.product_workspace import analyze_product_images


def test_image_analysis_keeps_unknown_size_explicit():
    result = analyze_product_images(
        {"images": [{"url": "https://example.com/product.webp", "alt": "", "width": None, "height": None}]},
        primary_image_url=None,
    )
    assert result[0].issues == ["missing_alt", "dimensions_unknown"]
    assert "large_dimensions_review" not in result[0].issues


def test_image_analysis_flags_same_source_variants_without_claiming_file_size():
    result = analyze_product_images(
        {"images": [
            {"url": "https://example.com/p.jpg?w=600", "alt": "Front", "width": 600, "height": 600},
            {"url": "https://example.com/p.jpg?w=1200", "alt": "Front", "width": 1200, "height": 1200},
        ]}, primary_image_url=None,
    )
    assert all("duplicate_source" in item.issues for item in result)
    assert all("file_size" not in issue for item in result for issue in item.issues)


def test_primary_image_is_not_invented_when_no_image_was_observed():
    assert analyze_product_images({}, primary_image_url=None) == []
