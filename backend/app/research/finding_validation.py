from app.models.base import utcnow
from app.models.finding import Finding, FindingStatus

# Part G-B3 — replaces the old blind "+/-0.15 per validate_finding call"
# step. That mechanism let the SAME source (Google) be re-checked several
# times and still never cross the validated threshold on its own, which is
# exactly why G-A showed validated_findings=0 across all five stores: no
# finding ever accumulated agreement from a SECOND, independent source.
# Every state change now goes through record_evidence_check(), so
# confidence is always traceable to which sources were checked and what
# each one concluded — never an opaque number.
CONTRADICTED_THRESHOLD = 0.3
SUPPORTED_THRESHOLD = 0.6
VALIDATED_THRESHOLD = 0.7
MIN_SOURCES_FOR_FULL_VALIDATION = 2

VALID_SOURCES = ("store", "google", "chatgpt", "competitor_page")


def _compute_confidence(checked: dict) -> float:
    total = len(checked)
    if total == 0:
        return 0.5
    supports = sum(1 for v in checked.values() if v.get("supports"))
    contradicts = total - supports
    if contradicts > supports:
        return max(0.0, 0.5 - 0.2 * contradicts)
    if supports > contradicts:
        if total == 1:
            return 0.65  # one supporting source: more likely true, not yet multi-source validated
        return min(1.0, 0.5 + 0.2 * supports)
    return 0.5  # tied — genuinely mixed signal, not evidence of anything


def _derive_status(confidence: float, total_checked: int) -> FindingStatus:
    if total_checked == 0:
        return FindingStatus.candidate  # hypothesis — nothing checked yet
    if confidence <= CONTRADICTED_THRESHOLD:
        return FindingStatus.rejected  # "contradicted" — even one clear counter-signal is enough to reject
    if confidence >= VALIDATED_THRESHOLD and total_checked >= MIN_SOURCES_FOR_FULL_VALIDATION:
        return FindingStatus.validated
    if confidence >= SUPPORTED_THRESHOLD:
        return FindingStatus.supported
    return FindingStatus.insufficient_evidence


def _explain(checked: dict) -> str:
    if not checked:
        return "فرضية أولية — لم يُتحقق منها بعد"
    parts = []
    for source, v in checked.items():
        verdict = "يدعم" if v.get("supports") else "يعارض"
        detail = v.get("detail", "")
        parts.append(f"{source}: {verdict}" + (f" ({detail})" if detail else ""))
    return "؛ ".join(parts)


def record_evidence_check(finding: Finding, *, source: str, supports: bool, detail: str = "") -> Finding:
    """The one place a Finding's validation state changes. `source` is one
    of VALID_SOURCES (store/google/chatgpt/competitor_page) — re-checking
    the same source again overwrites that source's entry (latest check
    wins for that source) rather than double-counting it, so confidence
    always reflects 'how many independent sources agree', not 'how many
    times someone happened to call validate_finding'.
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"unknown evidence source '{source}' — expected one of {VALID_SOURCES}")

    breakdown = dict(finding.evidence_breakdown or {})
    breakdown[source] = {"checked": True, "supports": supports, "detail": detail}
    finding.evidence_breakdown = breakdown

    checked = {k: v for k, v in breakdown.items() if v.get("checked")}
    confidence = _compute_confidence(checked)

    finding.confidence = confidence
    finding.confidence_explanation = _explain(checked)
    finding.validation_count += 1
    finding.last_validated_at = utcnow()
    finding.status = _derive_status(confidence, len(checked))

    return finding
