import uuid
from dataclasses import dataclass

from app.models.recommendation import Recommendation

# Part Q3 — the recommendation-quality checklist from the directive (point
# 42): top recommendations must contain no raw page titles, garbage
# intents, duplicate recommendations, unsupported claims, irrelevant
# competitors, or generic SEO advice. Irrelevant competitors are prevented
# upstream (app.opportunities.detectors filters by
# app.competitors.classification.is_business_competitor) and garbage
# intents upstream too (app.intent.quality's G-B1 gate) — this module is
# the last-line, deterministic check over the *generated Recommendation
# text itself*, run over whatever batch is about to be shown to the store
# owner (typically the primary queue).

# Same heuristic as app.intent.quality._looks_like_scraped_title — a
# pipe-separated or heavily comma-enumerated string reads like a raw page/
# product title, never something a template or a human would write as a
# recommendation title.
def _looks_like_scraped_title(text: str) -> bool:
    if "|" in text:
        return True
    return text.count(",") >= 2 or text.count("،") >= 2


# The exact fallback text app.opportunities.implementation_templates._build_generic
# emits for any opportunity_type without a bespoke template — the one
# literal place actual generic advice can still reach a customer.
_GENERIC_FALLBACK_STEP = "راجع تفاصيل هذه الفرصة واتخذ إجراءً مناسبًا"

NEAR_DUPLICATE_TITLE_JACCARD_THRESHOLD = 0.8


@dataclass
class QualityIssue:
    recommendation_id: uuid.UUID
    check: str
    detail: str


def _normalize_title(title: str) -> set[str]:
    return set(title.strip().lower().split())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def check_recommendation_batch_quality(recommendations: list[Recommendation]) -> list[QualityIssue]:
    """Runs every check over one batch (e.g. the primary queue about to be
    shown to a store owner). Deterministic, no AI, no DB access — pure
    inspection of already-generated Recommendation rows. Empty return
    means the batch is clean."""
    issues: list[QualityIssue] = []

    for rec in recommendations:
        if _looks_like_scraped_title(rec.title):
            issues.append(QualityIssue(rec.id, "raw_page_title", f"title reads like a scraped page title: {rec.title!r}"))
        if _looks_like_scraped_title(rec.what_to_do):
            issues.append(
                QualityIssue(rec.id, "raw_page_title", f"what_to_do reads like a scraped page title: {rec.what_to_do!r}")
            )

        if len(set(rec.evidence_ids)) < 2:
            issues.append(QualityIssue(rec.id, "unsupported_claim", "no evidence_ids — the recommendation cites no evidence"))

        if rec.implementation_steps == [_GENERIC_FALLBACK_STEP]:
            issues.append(QualityIssue(rec.id, "generic_advice", "fell through to the generic fallback template"))

    seen_titles: list[tuple[uuid.UUID, set[str]]] = []
    for rec in recommendations:
        tokens = _normalize_title(rec.title)
        for other_id, other_tokens in seen_titles:
            if _jaccard(tokens, other_tokens) >= NEAR_DUPLICATE_TITLE_JACCARD_THRESHOLD:
                issues.append(
                    QualityIssue(rec.id, "duplicate_recommendation", f"near-duplicate title of recommendation {other_id}")
                )
                break
        seen_titles.append((rec.id, tokens))

    return issues
