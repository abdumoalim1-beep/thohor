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
from collections import defaultdict

from sqlmodel import Session

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


def _top_missing_subject(missing: list[dict]) -> dict | None:
    counts: dict[str, int] = defaultdict(int)
    for entry in missing:
        if entry.get("subject"):
            counts[entry["subject"]] += 1
    if not counts:
        return None
    subject = max(counts, key=counts.get)
    return {"subject": subject, "count": counts[subject]}


def _evidence_queries(missing: list[dict], *, limit: int = 2) -> list[str]:
    return [m["query"] for m in missing[:limit]]


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
        "evidence": _evidence_queries(missing),
    }


async def build_recommendation(
    *, session: Session, router: ModelRouter, understanding: dict, enriched_queries: list[dict]
) -> dict:
    missing = build_missing_query_evidence(enriched_queries)
    if not missing:
        return _fallback_recommendation(missing, understanding=understanding)

    top = _top_missing_subject(missing)
    topic = top["subject"] if top else None
    evidence = _evidence_queries(missing)
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
