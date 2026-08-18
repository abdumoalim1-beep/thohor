import re
import uuid
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.models.ai_visibility import AIVisibilityObservation
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.intent import Intent
from app.models.page_intelligence import PageGapAnalysis
from app.models.serp import SerpObservation

"""Part R2-F4 (Round 2 remediation) — Evidence Scope Integrity Check.

Confirmed root cause (jarir.com, recommendation dc804982-a6ec-4aee-900d-
db96bd7e757c): Part R5's semantic recommendation dedup (app.opportunities.
dedup) judged five distinct product-specific google_visibility_gap
recommendations (Apple/Roku/Ring/Microsoft/generic-tech products) as the
same real-world duplicate — same opportunity_type, a near-identical
action-template sentence (only the quoted topic name differs, so token
Jaccard stays high), and a shared Q1 intent cluster (all landed under a
broad category) — then unioned every member's evidence_ids into the
highest-priority survivor. The result: a recommendation titled about Apple
products backed entirely by evidence about Roku/Ring/Microsoft. Confirmed
via recommendation_history: four `superseded_duplicate` rows all pointing
`superseded_by` at the Apple recommendation.

This module is a general, additive safety net — it does not change R5's
duplicate-detection judgment (dedup.py's is_semantic_duplicate is untouched,
per the phase rule to preserve R1-R8) — applied wherever a Recommendation's
evidence set is finalized: whatever evidence ends up attached, only
evidence whose own backing observation is about the same intent/topic the
recommendation/opportunity itself declares (its own affected_intents/
target_intents, resolved structurally — see target_topic_from_intents)
survives. This directly implements the remediation directive's rule: when
merging intents/queries, never silently widen evidence scope.
"""

_ARABIC_STOPWORDS = {
    "من", "في", "على", "الى", "إلى", "و", "أو", "او", "ما", "هو", "هي",
    "لي", "لك", "عن", "مع", "هذا", "هذه", "التي", "الذي", "يا",
}

# Generic commerce nouns that appear inside almost every intent topic
# regardless of the actual product/category (e.g. 'منتجات أبل' / 'منتجات
# روكو' both contain 'منتجات') — excluded from the overlap signal for the
# same reason Part R2-F2/R2-F3 exclude them: a shared generic word is not
# evidence of a shared topic, and treating it as such would silently
# re-open the exact bug this module exists to close.
_GENERIC_TOPIC_WORDS = {
    "منتجات", "منتج", "المنتجات", "المنتج", "قسم", "أقسام", "تصنيف",
    "تصنيفات", "فئة", "فئات", "products", "product", "category", "categories",
}


def _tokens(text: str) -> set[str]:
    normalized = re.sub(r"[^\w\s]", " ", text or "", flags=re.UNICODE).lower()
    return {
        t for t in normalized.split()
        if t not in _ARABIC_STOPWORDS and t not in _GENERIC_TOPIC_WORDS and len(t) > 1
    }


def _evidence_own_topics(session: Session, evidence: Evidence) -> set[str]:
    """The specific topic the evidence's own backing observation is
    actually about — resolved structurally through the observation's
    intent (never by parsing free text, which is fragile and gameable).

    Deliberately uses Intent.topic only, never Intent.category: category is
    intentionally broad (e.g. 'إلكترونيات'), and two genuinely different
    products (Apple / Roku) share it — matching on category would silently
    re-open the exact jarir.com bug this check exists to close (Part R2-F3
    learned the identical lesson about generic/category-level overlap being
    too coarse a relevance signal)."""
    intent: Intent | None = None
    if evidence.source_type == EvidenceSourceType.serp_observation:
        obs = session.get(SerpObservation, evidence.source_id)
        if obs is not None:
            intent = session.get(Intent, obs.intent_id)
    elif evidence.source_type == EvidenceSourceType.ai_visibility_observation:
        obs = session.get(AIVisibilityObservation, evidence.source_id)
        if obs is not None:
            intent = session.get(Intent, obs.intent_id)
    elif evidence.source_type == EvidenceSourceType.page_gap_analysis:
        analysis = session.get(PageGapAnalysis, evidence.source_id)
        if analysis is not None:
            intent = session.get(Intent, analysis.intent_id)

    if intent is None or not intent.topic:
        return set()
    return {intent.topic}


def _resolve_intents(session: Session, stable_intent_ids: list[str]) -> list[Intent]:
    """Resolves stable_intent_id strings (Opportunity.affected_intents /
    Recommendation.target_intents — Part F.5-0's cross-run identity) to
    their most-recent per-run Intent row — same resolution pattern as
    app.opportunities.dedup._intent_cluster_ids, since a fresh Intent row
    is created every research run."""
    intents: list[Intent] = []
    for raw in stable_intent_ids:
        try:
            stable_intent_id = uuid.UUID(str(raw))
        except (ValueError, TypeError):
            continue
        intent = session.exec(
            select(Intent)
            .where(Intent.stable_intent_id == stable_intent_id)
            .order_by(Intent.created_at.desc())  # type: ignore[attr-defined]
        ).first()
        if intent is not None:
            intents.append(intent)
    return intents


def target_topic_from_intents(session: Session, stable_intent_ids: list[str]) -> str:
    """The specific topic(s) a Recommendation or Opportunity is actually
    about, resolved structurally from its own affected_intents/
    target_intents — no persisted Opportunity.fingerprint_target field
    exists (it's a transient OpportunityDraft field only), and no free-text
    parsing is needed since the intent link is already there. Intent.topic
    only (see _evidence_own_topics for why category is excluded) — for a
    multi-intent category_visibility_gap opportunity this naturally unions
    every affected intent's own specific topic, which is exactly the set
    its own evidence is drawn from."""
    topics: set[str] = set()
    for intent in _resolve_intents(session, stable_intent_ids):
        if intent.topic:
            topics.add(intent.topic)
    return " ".join(sorted(topics))


@dataclass
class EvidenceScopeResult:
    aligned_evidence_ids: list[str] = field(default_factory=list)
    dropped_evidence_ids: list[str] = field(default_factory=list)
    scope_score: float = 1.0  # aligned / considered; 1.0 when nothing was checkable


def check_evidence_scope(session: Session, target_topic: str, evidence_ids: list[str]) -> EvidenceScopeResult:
    """Filters evidence_ids down to evidence whose own backing intent/topic
    shares real token overlap with target_topic (typically built by
    target_topic_from_intents from the recommendation/opportunity's own
    affected_intents/target_intents).

    Evidence that can't be resolved to a specific intent (unknown source
    type, missing row, or either side has no comparable tokens) is kept —
    this check only ever narrows scope for evidence it can positively
    verify is about a *different* topic; it never penalizes evidence it
    can't classify.
    """
    if not evidence_ids:
        return EvidenceScopeResult(scope_score=1.0)

    target_tokens = _tokens(target_topic)
    aligned: list[str] = []
    dropped: list[str] = []
    for raw_id in evidence_ids:
        try:
            evidence_uuid = uuid.UUID(str(raw_id))
        except (ValueError, TypeError):
            aligned.append(raw_id)
            continue
        evidence = session.get(Evidence, evidence_uuid)
        if evidence is None:
            dropped.append(raw_id)
            continue
        own_topics = _evidence_own_topics(session, evidence)
        if not own_topics or not target_tokens:
            aligned.append(raw_id)
            continue
        own_tokens = {t for topic in own_topics for t in _tokens(topic)}
        if own_tokens & target_tokens:
            aligned.append(raw_id)
        else:
            dropped.append(raw_id)

    total = len(aligned) + len(dropped)
    scope_score = (len(aligned) / total) if total else 1.0
    return EvidenceScopeResult(aligned_evidence_ids=aligned, dropped_evidence_ids=dropped, scope_score=scope_score)
