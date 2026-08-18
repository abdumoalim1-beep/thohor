from app.store_intelligence.product_workspace import (
    completion_score,
    implementation_fields,
    product_page_checks,
)


def test_product_checks_preserve_unknown_fields_as_missing():
    checks = product_page_checks({}, image_url=None)

    assert completion_score(checks) == 0
    assert all(check.status == "missing" for check in checks)
    assert not any(check.current_value for check in checks)


def test_product_checks_only_mark_observed_page_facts_present():
    extraction = {
        "title": "منتج مؤكد",
        "h1": "منتج مؤكد",
        "canonical": "https://example.com/products/1",
        "meta_description": "وصف مؤكد",
        "internal_links": ["https://example.com/c/one", "https://example.com/c/two"],
        "json_ld": [{"@type": "Product", "name": "منتج مؤكد"}],
    }
    checks = product_page_checks(extraction, image_url="https://example.com/image.webp")

    assert completion_score(checks) == 78
    assert next(check for check in checks if check.key == "faq_schema").status == "missing"


def test_implementation_fields_never_invents_missing_copy():
    result = implementation_fields({"meta_title": "عنوان مقترح"})

    assert result == {"title": "عنوان مقترح"}
    assert "faq" not in result
    assert "meta_description" not in result


def test_user_draft_overrides_generated_copy():
    result = implementation_fields({
        "on_demand": {"rebuild": {"title": "عنوان مولد", "h1": "H1 مولد"}},
        "user_draft": {"title": "عنوان عدله المستخدم"},
    })

    assert result["title"] == "عنوان عدله المستخدم"
    assert result["h1"] == "H1 مولد"
