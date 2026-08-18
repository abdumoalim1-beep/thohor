import dataclasses
import uuid

from sqlmodel import Session

from app.models.base import utcnow
from app.models.opportunity import Opportunity, OpportunityStatus
from app.opportunities.scoring import compute_priority_score


def _shares_an_intent(a: Opportunity, b: Opportunity) -> bool:
    return bool(set(a.affected_intents) & set(b.affected_intents))


def _group_by_shared_intent(opportunities: list[Opportunity]) -> list[list[Opportunity]]:
    """Connected components over the 'shares >=1 affected_intent' graph —
    transitive, so A-B-C all merge into one group even if A and C don't
    directly share an intent themselves, as long as B bridges them.
    Opportunities with no affected_intents at all (e.g. a category-level
    detector with no single intent) never group with anything — an empty
    set can never overlap another set."""
    groups: list[list[Opportunity]] = []
    for opportunity in opportunities:
        if not opportunity.affected_intents:
            groups.append([opportunity])
            continue
        matched_group = next(
            (g for g in groups if any(_shares_an_intent(opportunity, member) for member in g)), None
        )
        if matched_group is not None:
            matched_group.append(opportunity)
        else:
            groups.append([opportunity])

    # A single pass can miss a transitive bridge discovered later (A joins
    # on B, then C should have joined on A but B came first) — repeat
    # until stable. N is always small (one run's opportunities), so this
    # is cheap.
    changed = True
    while changed:
        changed = False
        merged: list[list[Opportunity]] = []
        for group in groups:
            target = next(
                (g for g in merged if any(_shares_an_intent(m1, m2) for m1 in group for m2 in g)), None
            )
            if target is not None:
                target.extend(group)
                changed = True
            else:
                merged.append(group)
        groups = merged

    return groups


def consolidate_opportunities(
    session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID, opportunities: list[Opportunity]
) -> list[Opportunity]:
    """Part Q2 — merges opportunities from different detectors that target
    the same underlying intent(s) (e.g. google_visibility_gap +
    missing_landing_page + ai_citation_gap all firing for 'قهوة مختصة')
    into one, instead of surfacing near-duplicate customer-facing
    opportunities for the same real-world gap. Deterministic: the
    highest-priority_score member of each group survives (status stays
    `open`); every other member is marked `merged` with merged_into_id set,
    and the survivor's evidence_ids/finding_ids/affected_* are the union
    across the whole group so it carries the *combined* evidence trail, not
    just its own detector's slice. Gap dimensions (google_visibility_gap
    etc.) take the max across the group — the honest combination rule: a
    merged opportunity is real if ANY contributing signal found it, and
    averaging would just dilute a strong signal with a weak one.

    Returns only the surviving (still status=open) opportunities from the
    input list, sorted by priority_score desc — the same contract
    run_opportunity_discovery_agent's callers already rely on.

    Known scope limitation (documented, not an oversight): title/
    description stay whatever the surviving detector originally wrote
    (Part E3's deterministic per-opportunity_type templates) — they don't
    get rewritten to mention every merged-in signal. Rephrasing customer-
    facing copy to summarize multiple detectors is Recommendation-quality
    work (Part Q3), not opportunity bookkeeping.
    """
    only_open = [o for o in opportunities if o.status == OpportunityStatus.open]
    groups = _group_by_shared_intent(only_open)

    survivors: list[Opportunity] = []
    for group in groups:
        if len(group) == 1:
            survivors.append(group[0])
            continue

        group_sorted = sorted(group, key=lambda o: o.priority_score, reverse=True)
        primary, rest = group_sorted[0], group_sorted[1:]

        def _union(field: str) -> list[str]:
            seen: list[str] = []
            for member in group_sorted:
                for value in getattr(member, field):
                    if value not in seen:
                        seen.append(value)
            return seen

        primary.affected_intents = _union("affected_intents")
        primary.affected_queries = _union("affected_queries")
        primary.affected_pages = _union("affected_pages")
        primary.affected_products = _union("affected_products")
        primary.competitors = _union("competitors")
        primary.evidence_ids = _union("evidence_ids")
        primary.finding_ids = _union("finding_ids")
        primary.google_visibility_gap = max(m.google_visibility_gap for m in group_sorted)
        primary.ai_visibility_gap = max(m.ai_visibility_gap for m in group_sorted)
        primary.competitor_gap = max(m.competitor_gap for m in group_sorted)
        primary.estimated_impact = max(m.estimated_impact for m in group_sorted)
        primary.confidence = max(m.confidence for m in group_sorted)
        primary.commercial_relevance = max(m.commercial_relevance for m in group_sorted)
        # Re-score after merging — the gap dimensions above may have moved
        # (max across the group can only raise them), so the pre-merge
        # priority_score would understate a merged opportunity's real
        # priority otherwise.
        breakdown = compute_priority_score(primary)
        primary.priority_score = breakdown.priority_score
        primary.score_breakdown = dataclasses.asdict(breakdown)
        primary.updated_at = utcnow()
        session.add(primary)

        for member in rest:
            member.status = OpportunityStatus.merged
            member.merged_into_id = primary.id
            member.updated_at = utcnow()
            session.add(member)

        session.commit()
        session.refresh(primary)
        survivors.append(primary)

    survivors.sort(key=lambda o: o.priority_score, reverse=True)
    return survivors
