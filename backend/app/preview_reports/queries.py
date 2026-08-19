"""Stage 4 (spec) — template-based search-query generation for a
PreviewReport. Deliberately NOT free-form LLM generation: every query is a
fixed intent template filled with a real category/product name extracted
in Stage 3 (app.preview_reports.understanding), so a query can never
reference something the store doesn't actually sell. No AI call in this
module at all — pure, fast, and fully reproducible, which also means this
stage can never be the reason a report is slow or flaky.

{location}/{use_case} template slots from the spec's own examples are
intentionally omitted here — this module has no reliably-extracted
location or use-case signal, and inventing one would violate the same
"never invent, doesn't rely on unextracted info" validation rule the spec
asks for. Add them only once a real signal for either exists.

TARGET_QUERY_COUNT (30) is this function's own default target_count, used
as-is by callers that want one shared query set for both search legs.
app.preview_reports.orchestration calls with the larger
settings.preview_search_ai_query_count instead, since the AI leg is now
allowed more queries than Google (see app.preview_reports.search) — quality
beats hitting the exact count either way: generate_search_queries() returns
however many valid, deduped queries exist, capped at the target, and never
pads with weak ones."""

import re

CATEGORY_TEMPLATES = [
    "أفضل {category}",
    "أفضل متجر {category}",
    "وين ألقى {category}",
    "مقارنة بين أنواع {category}",
]

PRODUCT_TEMPLATES = [
    "أفضل {product}",
    "وين ألقى {product}",
    "من وين أشتري {product}",
    "وش أفضل {product}",
    "أفضل مكان لشراء {product}",
]

TARGET_QUERY_COUNT = 30
MIN_SUBJECT_LENGTH = 2
_GENERIC_SUBJECT_MARKERS = (
    "uncategorized", "غير مصنف", "منتجات", "الرئيسية", "home", "shop",
    "store", "متجر", "all products", "كل المنتجات", "بدون تصنيف",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_valid_subject(name: str) -> bool:
    """Rejects subjects that are too generic/incomprehensible to make a
    real buyer search query out of — the spec's pre-run validation rules
    (not too generic, not incomprehensible), applied at the subject level
    since every candidate query is 100% determined by its subject."""
    cleaned = _normalize(name)
    if len(cleaned) < MIN_SUBJECT_LENGTH:
        return False
    lowered = cleaned.lower()
    if any(marker in lowered for marker in _GENERIC_SUBJECT_MARKERS):
        return False
    if not any(ch.isalpha() for ch in cleaned):
        return False
    return True


def generate_search_queries(
    facts: dict, target_count: int = TARGET_QUERY_COUNT, *, fallback_category: str | None = None
) -> list[dict]:
    """facts: the dict from app.preview_reports.understanding.
    extract_deterministic_facts() (needs category_names/product_names).
    Returns up to target_count dicts: {query, subject_type, subject,
    template}, deduped and interleaved across templates for breadth.

    fallback_category: the one-shot LLM understanding step's resolved
    category (app.preview_reports.understanding.build_understanding),
    used only when the deterministic crawl found zero valid category
    subjects on its own — e.g. a store whose crawl budget never reached a
    real category page. Never used to invent product subjects, only the
    single broad category already grounded in the store's own title/meta
    text; still runs through the same validity filter as everything
    else."""
    categories = [c for c in facts.get("category_names", []) if _is_valid_subject(c)]
    products = [p for p in facts.get("product_names", []) if _is_valid_subject(p)]
    if not categories and fallback_category and _is_valid_subject(fallback_category):
        categories = [fallback_category]

    candidates: list[dict] = []
    for template in CATEGORY_TEMPLATES:
        for category in categories:
            candidates.append({
                "query": _normalize(template.format(category=category)),
                "subject_type": "category",
                "subject": category,
                "template": template,
            })
    for template in PRODUCT_TEMPLATES:
        for product in products:
            candidates.append({
                "query": _normalize(template.format(product=product)),
                "subject_type": "product",
                "subject": product,
                "template": template,
            })

    by_template: dict[str, list[dict]] = {}
    for candidate in candidates:
        by_template.setdefault(candidate["template"], []).append(candidate)

    ordered: list[dict] = []
    seen_queries: set[str] = set()
    while len(ordered) < target_count:
        progressed = False
        for bucket in by_template.values():
            if not bucket:
                continue
            item = bucket.pop(0)
            progressed = True
            key = item["query"].casefold()
            if key in seen_queries:
                continue
            seen_queries.add(key)
            ordered.append(item)
            if len(ordered) >= target_count:
                break
        if not progressed:
            break

    return ordered[:target_count]
