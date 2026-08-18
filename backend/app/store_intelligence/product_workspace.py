from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class ProductPageCheck:
    key: str
    label: str
    status: str
    current_value: str | None
    message: str


@dataclass(frozen=True)
class ProductImageInsight:
    url: str
    alt: str | None
    width: int | None
    height: int | None
    issues: list[str]
    status: str


def analyze_product_images(extraction: dict[str, Any], *, primary_image_url: str | None) -> list[ProductImageInsight]:
    """Analyze observable attributes only; file byte-size is never inferred."""
    raw_images = extraction.get("images") or []
    images = [item for item in raw_images if isinstance(item, dict) and _text(item.get("url"))]
    if primary_image_url and not any(item.get("url") == primary_image_url for item in images):
        images.insert(0, {"url": primary_image_url, "alt": None, "width": None, "height": None})
    counts: dict[str, int] = {}
    for image in images:
        identity = _image_identity(str(image["url"]))
        counts[identity] = counts.get(identity, 0) + 1
    result: list[ProductImageInsight] = []
    for image in images:
        url = str(image["url"])
        alt = _text(image.get("alt"))
        width, height = _positive_int(image.get("width")), _positive_int(image.get("height"))
        issues: list[str] = []
        if not alt:
            issues.append("missing_alt")
        if width is None or height is None:
            issues.append("dimensions_unknown")
        elif width < 600 or height < 600:
            issues.append("small_dimensions")
        elif width > 2400 or height > 2400:
            issues.append("large_dimensions_review")
        if counts[_image_identity(url)] > 1:
            issues.append("duplicate_source")
        result.append(ProductImageInsight(url, alt, width, height, issues, "ready" if not issues else "review"))
    return result


def _image_identity(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _schema_entries(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    entries = extraction.get("json_ld") or []
    return [entry for entry in entries if isinstance(entry, dict)]


def _has_schema(extraction: dict[str, Any], schema_type: str) -> bool:
    for entry in _schema_entries(extraction):
        raw_type = entry.get("@type")
        types = [raw_type] if isinstance(raw_type, str) else raw_type or []
        if schema_type in types:
            return True
        graph = entry.get("@graph") or []
        if isinstance(graph, list) and any(isinstance(item, dict) and item.get("@type") == schema_type for item in graph):
            return True
    return False


def product_page_checks(extraction: dict[str, Any], *, image_url: str | None) -> list[ProductPageCheck]:
    title = _text(extraction.get("title"))
    h1 = _text(extraction.get("h1"))
    meta = _text(extraction.get("meta_description"))
    canonical = _text(extraction.get("canonical"))
    links = extraction.get("internal_links") or []
    images = extraction.get("images") or []
    observed_images = [image for image in images if isinstance(image, dict) and image.get("url")]
    images_with_alt = [image for image in observed_images if _text(image.get("alt"))]

    return [
        _presence("title", "عنوان الصفحة", title, "لم نرصد عنوان الصفحة بعد."),
        _presence("meta_description", "وصف نتيجة البحث", meta, "لا يوجد Meta description مؤكد في آخر قراءة."),
        _presence("h1", "العنوان الرئيسي H1", h1, "لا يوجد H1 مؤكد في آخر قراءة."),
        _presence("canonical", "الرابط الأساسي Canonical", canonical, "لم نرصد رابط Canonical مؤكدًا."),
        _boolean("product_schema", "بيانات Product المنظمة", _has_schema(extraction, "Product") or _has_schema(extraction, "ProductGroup"), "لم نرصد Product Schema."),
        _boolean("faq_schema", "الأسئلة الشائعة", _has_schema(extraction, "FAQPage"), "لم نرصد FAQ Schema."),
        _boolean("image", "صورة المنتج", bool(image_url), "لم نرصد صورة مؤكدة للمنتج."),
        _boolean(
            "image_alt", "النص البديل للصور",
            bool(observed_images) and len(images_with_alt) == len(observed_images),
            "بعض الصور المرصودة لا تحمل نصًا بديلًا مؤكدًا.",
        ),
        _boolean("internal_links", "الروابط الداخلية", isinstance(links, list) and len(links) >= 2, "الصفحة لا تعرض روابط داخلية كافية في البيانات المرصودة."),
    ]


def general_page_checks(extraction: dict[str, Any], *, page_type: str) -> list[ProductPageCheck]:
    checks = [
        _presence("title", "عنوان الصفحة", _text(extraction.get("title")), "لم نرصد عنوانًا للصفحة."),
        _presence("meta_description", "وصف نتيجة البحث", _text(extraction.get("meta_description")), "لم نرصد Meta description."),
        _presence("h1", "العنوان الرئيسي H1", _text(extraction.get("h1")), "لم نرصد H1."),
        _presence("canonical", "الرابط الأساسي Canonical", _text(extraction.get("canonical")), "لم نرصد Canonical."),
        _boolean("internal_links", "الروابط الداخلية", len(extraction.get("internal_links") or []) >= 2, "لم نرصد رابطين داخليين على الأقل."),
    ]
    if page_type == "product":
        checks.append(_boolean("product_schema", "بيانات Product المنظمة", _has_schema(extraction, "Product") or _has_schema(extraction, "ProductGroup"), "لم نرصد Product Schema."))
    if page_type in {"category", "content"}:
        checks.append(_boolean("sections", "بنية الأقسام", bool(extraction.get("h2")), "لم نرصد عناوين H2 توضح بنية الصفحة."))
    return checks


def completion_score(checks: list[ProductPageCheck]) -> int:
    if not checks:
        return 0
    passed = sum(check.status == "present" for check in checks)
    return round(passed / len(checks) * 100)


def extract_product_description(extraction: dict[str, Any]) -> str | None:
    for entry in _schema_entries(extraction):
        raw_type = entry.get("@type")
        types = [raw_type] if isinstance(raw_type, str) else raw_type or []
        if "Product" in types or "ProductGroup" in types:
            return _text(entry.get("description"))
    return None


def implementation_fields(package: dict[str, Any] | None) -> dict[str, Any]:
    """Expose existing implementation content only; never synthesize copy."""
    package = package or {}
    generated = package.get("on_demand") or {}
    rebuild = generated.get("rebuild") if isinstance(generated, dict) else None
    if isinstance(rebuild, dict):
        package = {**package, **rebuild}
    user_draft = package.get("user_draft")
    if isinstance(user_draft, dict):
        package = {**package, **user_draft}
    aliases = {
        "title": ("title", "meta_title", "page_title", "suggested_title"),
        "meta_description": ("meta_description", "suggested_meta_description"),
        "h1": ("h1", "suggested_h1"),
        "description": ("description", "product_description", "suggested_description"),
        "features": ("features", "benefits", "key_features"),
        "usage": ("usage", "how_to_use", "use_instructions"),
        "specifications": ("specifications", "specs", "attributes"),
        "image_alt": ("image_alt", "suggested_image_alt", "alt_text"),
        "h2": ("h2", "h2s", "h2_sections", "suggested_h2s", "suggested_h2_sections", "sections"),
        "faq": ("faq", "faqs", "faq_items", "faq_questions"),
        "internal_links": ("internal_links", "suggested_internal_links"),
        "instructions": ("instructions", "implementation_steps", "developer_instructions", "content_instructions", "steps"),
    }
    result: dict[str, Any] = {}
    for target, keys in aliases.items():
        for key in keys:
            value = package.get(key)
            if value not in (None, "", []):
                result[target] = value
                break
    return result


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _presence(key: str, label: str, value: str | None, missing: str) -> ProductPageCheck:
    return ProductPageCheck(key, label, "present" if value else "missing", value, "موجود في آخر قراءة." if value else missing)


def _boolean(key: str, label: str, present: bool, missing: str) -> ProductPageCheck:
    return ProductPageCheck(key, label, "present" if present else "missing", None, "موجود في آخر قراءة." if present else missing)
