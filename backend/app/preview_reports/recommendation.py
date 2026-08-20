"""Stage 11 (spec) — the PreviewReport's single recommendation. Evidence
is built entirely from queries where Stage 6/7's deterministic detector
already found brand_found is exactly False (a confirmed, successful
search that genuinely didn't surface the store) — never from `unknown` or
`failed` results, so the LLM is never handed ambiguous data and asked to
treat it as a real gap.

Retry philosophy (spec: "Attempt -> retry once when appropriate ->
degrade -> continue", never a long retry loop): ModelRouter.execute
already attempts the primary provider then one fallback provider before
raising, which satisfies "retry once" here without extra retry code. If
both fail, _fallback_recommendation() builds a small, honest
recommendation directly from the same missing-query evidence with no AI
call at all — a failed LLM call must never sink the whole report."""

import asyncio
import re
from collections import defaultdict

from sqlmodel import Session

from app.preview_reports.visibility import normalize_brand_text
from app.prompts.preview_recommendation import PREVIEW_RECOMMENDATION_PROMPT
from app.providers.ai.base import AIProviderError
from app.providers.ai.router import ModelRouter
from app.schemas.preview_recommendation import PreviewRecommendation

MAX_MISSING_QUERIES_SHOWN = 15
RECOMMENDATION_TIMEOUT_SECONDS = 20.0


def build_missing_query_evidence(enriched_queries: list[dict]) -> list[dict]:
    """Only genuinely-confirmed non-appearances — a successful search
    whose deterministic detector returned brand_found is False. `unknown`
    (ambiguous) and `failed` (technical failure) are excluded on purpose:
    neither is evidence the store 'didn't appear'."""
    missing: list[dict] = []
    for query in enriched_queries:
        google = query.get("google") or {}
        ai = query.get("ai") or {}
        missing_in = []
        if google.get("status") == "success" and google.get("brand_found") is False:
            missing_in.append("google")
        if ai.get("status") == "success" and ai.get("brand_found") is False:
            missing_in.append("ai")
        if missing_in:
            missing.append({
                "query": query["query"],
                "subject": query.get("subject"),
                "subject_type": query.get("subject_type"),
                "missing_in": missing_in,
            })
    return missing


_WORD_SPLIT = re.compile(r"\s+")


def _normalize_words(text: str) -> set[str]:
    """Splits into normalize_brand_text-normalized words, additionally
    stripping a leading definite-article "ال" so "العبايات" and "عبايات"
    count as the same word — plain substring matching would miss that."""
    words: set[str] = set()
    for raw in _WORD_SPLIT.split(text.strip()):
        word = normalize_brand_text(raw)
        if word.startswith("ال") and len(word) > 3:
            word = word[2:]
        if len(word) >= 2:
            words.add(word)
    return words


def _top_missing_subject(missing: list[dict]) -> dict | None:
    """Picks the subject with the most confirmed non-appearances. Ties
    (common for a store with weak visibility everywhere — every category
    equally "missing") used to just fall to dict-iteration order, i.e.
    whichever category the crawler happened to list first, with zero
    regard for whether it's the store's actual core product or a minor
    accessory/sub-brand page.

    Ties now break by "centrality": how often a subject's words recur
    across the store's OTHER missing subjects. A store's own category
    structure is real signal a brand_name/category text match isn't —
    tried matching against brand_name first, but a sub-brand collection
    literally named after the store (e.g. "كيان بريميوم" on a store
    called "كيان لأرقي العبايات") trivially "matches" the brand name
    without being a real product type. Word recurrence across the
    store's own categories doesn't have that false-positive: on that
    same real store, "عبايات" (abayas) recurs across 4 of its 6 real
    categories while "كيان"/"بريميوم" each appear exactly once, correctly
    surfacing "أحدث العبايات" / "كل العبايات" over both the sub-brand
    page and the accessory "عطر ومنديل عبايات" page. Final tie-break is
    the shortest subject name (a plain "كل العبايات" reads as more core
    than a longer, more qualified sub-category)."""
    counts: dict[str, int] = defaultdict(int)
    for entry in missing:
        if entry.get("subject"):
            counts[entry["subject"]] += 1
    if not counts:
        return None

    word_freq: dict[str, int] = defaultdict(int)
    subject_words_by_subject: dict[str, set[str]] = {}
    for subject in counts:
        words = _normalize_words(subject)
        subject_words_by_subject[subject] = words
        for word in words:
            word_freq[word] += 1

    def sort_key(subject: str) -> tuple[int, int, int]:
        words = subject_words_by_subject[subject]
        centrality = max((word_freq[w] for w in words), default=0)
        return (counts[subject], centrality, -len(words))

    subject = max(counts, key=sort_key)
    return {"subject": subject, "count": counts[subject]}


def _evidence_queries(missing: list[dict], *, subject: str | None = None, limit: int = 2) -> list[str]:
    """Queries actually about `subject` when one is given — otherwise the
    evidence can name a different, unrelated subject than the title/topic
    it's supposedly backing (this was a real, observed inconsistency once
    _top_missing_subject started picking by relevance instead of just
    "first in the list": both used to walk `missing` in the same order,
    so they silently agreed by accident)."""
    pool = [m for m in missing if m.get("subject") == subject] if subject else missing
    return [m["query"] for m in pool[:limit]]


def _fallback_recommendation(missing: list[dict], *, understanding: dict | None = None) -> dict:
    """No confirmed non-appearance to point at (either because the store
    had no valid product/category subject to search for, or every search
    that did run found the brand). Per spec, the report must never expose
    that the system came up short — this must read as ordinary, useful
    advice, not a "no data" admission. Grounds itself in the real
    category when one was resolved; only falls to fully generic copy when
    even that is missing."""
    top = _top_missing_subject(missing)
    if top is None:
        category = (understanding or {}).get("category") or ""
        if category:
            return {
                "title": f"خلّ صفحات {category} تجاوب على أسئلة العميل",
                "reason": (
                    f"متجرك يبيع ضمن فئة {category}، وفرصة الظهور تزيد لما تكون صفحاتها واضحة "
                    "بالتفاصيل اللي يبحث عنها العميل قبل الشراء."
                ),
                "action": "أضف لصفحاتك تفاصيل تساعد العميل يفهم الفروقات بين المنتجات ويعرف أيها يناسب احتياجه.",
                "topic": category,
                "evidence": [],
            }
        return {
            "title": "عزّز تواجد متجرك في نتائج البحث",
            "reason": "متجرك يحتاج محتوى أوضح في صفحاته الرئيسية يساعد العميل يفهم منتجاتك بسرعة.",
            "action": "راجع صفحات منتجاتك الرئيسية وتأكد أنها تحتوي أوصافًا واضحة تجيب على أسئلة العميل الشائعة.",
            "topic": None,
            "evidence": [],
        }
    subject = top["subject"]
    return {
        "title": f"قوّي ظهورك في نتائج البحث عن {subject}",
        "reason": f"متجرك لم يظهر في {top['count']} من عمليات البحث المرتبطة بـ{subject}، رغم أنها من المنتجات اللي تبيعها.",
        "action": f"قوّي صفحة {subject} في متجرك بمعلومات تساعد العميل قبل الشراء وتجيب على أسئلته الشائعة.",
        "topic": subject,
        "evidence": _evidence_queries(missing, subject=subject),
    }


async def build_recommendation(
    *, session: Session, router: ModelRouter, understanding: dict, enriched_queries: list[dict]
) -> dict:
    missing = build_missing_query_evidence(enriched_queries)
    if not missing:
        return _fallback_recommendation(missing, understanding=understanding)

    top = _top_missing_subject(missing)
    topic = top["subject"] if top else None
    evidence = _evidence_queries(missing, subject=topic)
    shown = missing[:MAX_MISSING_QUERIES_SHOWN]
    missing_lines = "\n".join(
        f"- \"{m['query']}\" (لم يظهر في: {'، '.join(m['missing_in'])})" for m in shown
    )
    messages = PREVIEW_RECOMMENDATION_PROMPT.render(
        brand_name=understanding.get("brand_name") or "",
        category=understanding.get("category") or "",
        total_missing=str(len(missing)),
        shown_missing=str(len(shown)),
        missing_queries=missing_lines,
    )
    try:
        response = await asyncio.wait_for(
            router.execute(
                session=session,
                task_type="preview_recommendation",
                messages=messages,
                prompt_name=PREVIEW_RECOMMENDATION_PROMPT.name,
                prompt_version=PREVIEW_RECOMMENDATION_PROMPT.version,
                schema_version=PREVIEW_RECOMMENDATION_PROMPT.schema_version,
                response_schema=PreviewRecommendation,
            ),
            timeout=RECOMMENDATION_TIMEOUT_SECONDS,
        )
    except (AIProviderError, RuntimeError, TimeoutError, asyncio.TimeoutError, ValueError):
        return _fallback_recommendation(missing, understanding=understanding)

    if response.parsed is None:
        return _fallback_recommendation(missing, understanding=understanding)

    recommendation = PreviewRecommendation.model_validate(response.parsed)
    return {
        "title": recommendation.title,
        "reason": recommendation.reason,
        "action": recommendation.action,
        "topic": topic,
        "evidence": evidence,
    }
