"""Part R5 (Round 1 remediation) — deterministic semantic recommendation
dedup. Two Recommendations can be the same real-world ask even when the
Opportunity-level fingerprint (store_id + opportunity_type + normalized
target *text*, see recommendation_engine._opportunity_fingerprint) doesn't
catch it — e.g. two intents that mean the same thing but were phrased
differently, or two opportunities that both ultimately point at the same
page. This module compares Recommendations structurally (opportunity_type,
target, action text, evidence overlap, and Q1's intent clusters) — no LLM
call, no new cost, fully deterministic and re-runnable.
"""

import re
import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models.base import utcnow
from app.models.intent import Intent
from app.models.opportunity import Opportunity
from app.models.recommendation import Recommendation, RecommendationHistory, RecommendationStatus
from app.opportunities.evidence_integrity import check_evidence_scope, target_topic_from_intents

# Deliberately lower than app.intent.clustering's CLUSTER_JACCARD_THRESHOLD
# (0.25) — action *phrasing* from the same deterministic template (Part E3)
# is either near-identical (same template, topic text swapped in) or
# clearly different (a different template entirely), so there's no fuzzy
# middle ground to tune for the way there is with free-text intent topics.
_ACTION_SIMILARITY_THRESHOLD = 0.6
# Majority-shared evidence, on its own (no cluster/target agreement needed),
# is treated as a strong-enough corroborating signal that two opportunities
# describe the same real-world gap — set higher than a cluster-corroborated
# match would need, since evidence overlap alone is the noisiest of the
# three signals below.
_EVIDENCE_OVERLAP_THRESHOLD = 0.5

# Same convention as app.intent.clustering / app.competitors.classification:
# each module keeps its own small copy of this helper rather than importing
# a "private" underscored function from another module.
_ARABIC_STOPWORDS = {
    "من", "في", "على", "الى", "إلى", "و", "أو", "او", "ما", "هو", "هي",
    "لي", "لك", "عن", "مع", "هذا", "هذه", "التي", "الذي", "يا",
}

_ACTIVE_STATUSES = frozenset(
    {
        RecommendationStatus.new,
        RecommendationStatus.planned,
        RecommendationStatus.in_progress,
        RecommendationStatus.monitoring,
        RecommendationStatus.implemented,
        RecommendationStatus.successful,
        RecommendationStatus.partial,
        RecommendationStatus.no_detectable_impact,
        RecommendationStatus.regressed,
    }
)
# dismissed/superseded are already resolved or retired — never re-merge
# something into (or out of) that state.


def _normalize_text(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text or "", flags=re.UNICODE).lower().split())


def _tokens(text: str) -> set[str]:
    return {t for t in _normalize_text(text).split() if t not in _ARABIC_STOPWORDS and len(t) > 1}


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class RecommendationSignature:
    opportunity_type: str
    normalized_target: str
    action_tokens: frozenset[str]
    evidence_ids: frozenset[str]
    intent_cluster_ids: frozenset[uuid.UUID]


def build_signature(
    *,
    opportunity_type: str,
    target_page: str | None,
    target_intents: list[str],
    what_to_do: str,
    evidence_ids: list[str],
    intent_cluster_ids: frozenset[uuid.UUID] = frozenset(),
) -> RecommendationSignature:
    normalized_target = (target_page or "").strip().lower().rstrip("/")
    if not normalized_target and target_intents:
        # No single page to anchor on (e.g. a category-level opportunity) —
        # fall back to the set of intents targeted, order-independent.
        normalized_target = "|".join(sorted(target_intents))
    return RecommendationSignature(
        opportunity_type=opportunity_type,
        normalized_target=normalized_target,
        action_tokens=frozenset(_tokens(what_to_do)),
        evidence_ids=frozenset(evidence_ids),
        intent_cluster_ids=intent_cluster_ids,
    )


def is_semantic_duplicate(a: RecommendationSignature, b: RecommendationSignature) -> bool:
    """True when `a` and `b` are the same real-world recommendation.

    Same opportunity_type AND a matching action (near-identical what_to_do
    phrasing) are both required up front — a different action for the same
    intent/target is a legitimately distinct recommendation, never a
    duplicate, no matter how much else lines up. Given those two hold, ANY
    ONE of the following is then sufficient: the exact same target (page,
    or — absent a page — the same set of intents); a shared intent cluster
    (Part Q1 — two intents phrased differently but grouped as the same
    topic); or majority-overlapping evidence (two independent detectors
    both pointing at the same underlying gap)."""
    if a.opportunity_type != b.opportunity_type:
        return False
    if _jaccard(a.action_tokens, b.action_tokens) < _ACTION_SIMILARITY_THRESHOLD:
        return False
    if a.normalized_target and a.normalized_target == b.normalized_target:
        return True
    if a.intent_cluster_ids & b.intent_cluster_ids:
        return True
    return _jaccard(a.evidence_ids, b.evidence_ids) >= _EVIDENCE_OVERLAP_THRESHOLD


def _intent_cluster_ids(session: Session, target_intents: list[str]) -> frozenset[uuid.UUID]:
    """target_intents (Opportunity.affected_intents / Recommendation's copy
    of it) holds *stable_intent_id* strings (Part F.5-0's cross-run identity
    — see detectors.py), never a per-run Intent.id, since a fresh Intent row
    is created every research run. Clustering (Part Q1) is per-run too, so
    this resolves each stable intent to whichever of its per-run Intent rows
    was clustered most recently."""
    ids: set[uuid.UUID] = set()
    for raw in target_intents:
        try:
            stable_intent_id = uuid.UUID(str(raw))
        except (ValueError, TypeError):
            continue
        intent = session.exec(
            select(Intent)
            .where(Intent.stable_intent_id == stable_intent_id)
            .where(Intent.cluster_id.is_not(None))  # type: ignore[union-attr]
            .order_by(Intent.created_at.desc())  # type: ignore[attr-defined]
        ).first()
        if intent is not None and intent.cluster_id is not None:
            ids.add(intent.cluster_id)
    return frozenset(ids)


def _signature_for(session: Session, recommendation: Recommendation) -> RecommendationSignature:
    opportunity = session.get(Opportunity, recommendation.opportunity_id)
    opportunity_type = opportunity.opportunity_type if opportunity is not None else ""
    return build_signature(
        opportunity_type=opportunity_type,
        target_page=recommendation.target_page,
        target_intents=recommendation.target_intents,
        what_to_do=recommendation.what_to_do,
        evidence_ids=recommendation.evidence_ids,
        intent_cluster_ids=_intent_cluster_ids(session, recommendation.target_intents),
    )


def _group_by_semantic_duplicate(
    items: list[Recommendation], signatures: dict[uuid.UUID, RecommendationSignature]
) -> list[list[Recommendation]]:
    """Connected components over the is_semantic_duplicate graph — same
    transitive-merge pattern as app.opportunities.consolidation's
    _group_by_shared_intent (A-B-C merge into one group even if A and C
    don't directly match, as long as B bridges them)."""
    groups: list[list[Recommendation]] = []
    for item in items:
        sig = signatures[item.id]
        matched = next(
            (g for g in groups if any(is_semantic_duplicate(sig, signatures[m.id]) for m in g)), None
        )
        if matched is not None:
            matched.append(item)
        else:
            groups.append([item])

    changed = True
    while changed:
        changed = False
        merged: list[list[Recommendation]] = []
        for group in groups:
            target = next(
                (
                    g
                    for g in merged
                    if any(is_semantic_duplicate(signatures[m1.id], signatures[m2.id]) for m1 in group for m2 in g)
                ),
                None,
            )
            if target is not None:
                target.extend(group)
                changed = True
            else:
                merged.append(group)
        groups = merged

    return groups


def consolidate_duplicate_recommendations(
    session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID
) -> list[Recommendation]:
    """Runs a semantic-dedup pass across ALL of the store's currently-active
    recommendations (not just the ones touched this run), so a duplicate
    pair created across two different research runs — or created before
    this fix existed at all — still collapses the next time this runs.
    Deterministic, no AI call.

    The higher-priority_score member of each duplicate group survives
    (status untouched); every other member is marked `superseded` (an
    existing RecommendationStatus value from Part E0/R2 that was defined
    but never actually set anywhere until now) with a RecommendationHistory
    row recording which recommendation superseded it, and its evidence_ids/
    confidence/priority_score are folded into the survivor so no signal is
    lost. `select_primary_recommendations` (Part R2) already filters to
    status == new, so a superseded duplicate stops being offered as a
    primary recommendation automatically — no other call site needs to
    change.

    Returns the surviving Recommendations (size == number of distinct
    real-world recommendations left after merging).
    """
    active = session.exec(
        select(Recommendation)
        .where(Recommendation.store_id == store_id)
        .where(Recommendation.status.in_(_ACTIVE_STATUSES))  # type: ignore[attr-defined]
    ).all()
    if len(active) < 2:
        return list(active)

    signatures = {rec.id: _signature_for(session, rec) for rec in active}
    groups = _group_by_semantic_duplicate(active, signatures)

    survivors: list[Recommendation] = []
    for group in groups:
        if len(group) == 1:
            survivors.append(group[0])
            continue

        group_sorted = sorted(group, key=lambda r: r.priority_score, reverse=True)
        primary, rest = group_sorted[0], group_sorted[1:]

        # Part R2-F4 — is_semantic_duplicate above can judge two
        # recommendations "the same real-world ask" via a shared intent
        # cluster even when they're about genuinely different specific
        # topics (e.g. 'Apple products' and 'Roku products' both landing
        # under a broad 'Electronics' cluster). Blindly unioning evidence
        # on merge then attaches off-topic evidence to the survivor. Only
        # fold in a member's evidence when it's actually about the
        # survivor's own declared target — never silently widen scope.
        target_topic = target_topic_from_intents(session, primary.target_intents)

        merged_evidence = list(primary.evidence_ids)
        for member in rest:
            scope = check_evidence_scope(session, target_topic, member.evidence_ids)
            for evidence_id in scope.aligned_evidence_ids:
                if evidence_id not in merged_evidence:
                    merged_evidence.append(evidence_id)
        primary.evidence_ids = merged_evidence
        primary.confidence = max(m.confidence for m in group_sorted)
        primary.priority_score = max(m.priority_score for m in group_sorted)
        primary.last_seen_research_run_id = research_run_id
        primary.updated_at = utcnow()
        session.add(primary)

        for member in rest:
            member.status = RecommendationStatus.superseded
            member.updated_at = utcnow()
            session.add(member)
            session.add(
                RecommendationHistory(
                    recommendation_id=member.id,
                    research_run_id=research_run_id,
                    event_type="superseded_duplicate",
                    snapshot={"superseded_by": str(primary.id)},
                )
            )

        session.commit()
        session.refresh(primary)
        survivors.append(primary)

    return survivors
