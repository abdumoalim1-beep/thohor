import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models.evidence import Evidence

"""Beta Readiness Remediation — Recommendation Confidence Model.

Directive requirement: confidence must not be "a mere AI opinion" (nor, as
it was before this module, a flat hand-set float per detector — e.g. every
google_visibility_gap opportunity got confidence=0.6 regardless of whether
it had one thin piece of evidence or five corroborating ones). Confidence is
now derived deterministically from properties of the evidence actually
attached to the recommendation: how much there is, how diverse its sources
are (a claim confirmed by both Google ranking data AND a real competitor
comparison is stronger than either alone), and whether it's backed by a
validated Finding or a named competitor.

No AI call, no free-text parsing — pure inspection of already-resolved
evidence_ids/finding_ids/competitor references, the same "deterministic,
inspectable, testable" posture as app.opportunities.scoring.
"""

HIGH_EVIDENCE_COUNT = 3
LOW_EVIDENCE_COUNT = 1


@dataclass
class ConfidenceResult:
    confidence: float
    tier: str  # "high" | "medium" | "low"
    evidence_count: int
    source_diversity: int


def _source_diversity(session: Session, evidence_ids: list[str]) -> int:
    types: set[str] = set()
    for raw_id in evidence_ids:
        try:
            evidence_uuid = uuid.UUID(str(raw_id))
        except (ValueError, TypeError):
            continue
        evidence = session.get(Evidence, evidence_uuid)
        if evidence is not None:
            types.add(evidence.source_type.value if hasattr(evidence.source_type, "value") else str(evidence.source_type))
    return len(types)


def compute_confidence(
    session: Session,
    evidence_ids: list[str],
    finding_ids: list[str],
    competitors: list[str],
) -> ConfidenceResult:
    """`evidence_ids` must be the FINAL, topic-scope-filtered list (what
    will actually be persisted on the Recommendation) — computing this
    against a pre-filter list would let evidence that's about to be dropped
    for being off-topic still inflate the confidence tier."""
    evidence_count = len(evidence_ids)
    diversity = _source_diversity(session, evidence_ids)
    has_finding = bool(finding_ids)
    has_competitor = bool(competitors)

    if evidence_count >= HIGH_EVIDENCE_COUNT or diversity >= 2 or (evidence_count >= 1 and has_finding and has_competitor):
        tier = "high"
        confidence = min(1.0, 0.75 + 0.05 * evidence_count)
    elif evidence_count >= 2 or (evidence_count == LOW_EVIDENCE_COUNT and (has_finding or has_competitor)):
        tier = "medium"
        confidence = 0.6
    elif evidence_count >= LOW_EVIDENCE_COUNT:
        tier = "low"
        confidence = 0.35
    else:
        # Should never be reached for a persisted, customer-visible
        # Recommendation post-remediation (zero evidence never gets this
        # far — see run_recommendation_engine) — kept as an honest floor
        # rather than raising, so a caller inspecting a draft/Opportunity
        # before the evidence gate runs gets a sane, clearly-low value.
        tier = "low"
        confidence = 0.0

    return ConfidenceResult(confidence=confidence, tier=tier, evidence_count=evidence_count, source_diversity=diversity)
