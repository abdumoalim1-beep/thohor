import dataclasses
import hashlib
import uuid

from sqlmodel import Session, select
from sqlalchemy.orm import defer

from app.measurement.baseline import capture_measurement_baseline
from app.models.base import utcnow
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.recommendation import Recommendation, RecommendationHistory, RecommendationStatus
from app.opportunities.confidence import compute_confidence
from app.opportunities.consolidation import consolidate_opportunities
from app.opportunities.dedup import consolidate_duplicate_recommendations
from app.opportunities.detectors import OPPORTUNITY_DETECTORS, OpportunityDraft
from app.opportunities.evidence_integrity import check_evidence_scope, target_topic_from_intents
from app.opportunities.implementation_templates import build_recommendation_content
from app.opportunities.scoring import compute_priority_score
from app.store_intelligence.catalog_resolution import resolve_catalog_targets


def _opportunity_fingerprint(store_id: uuid.UUID, opportunity_type: str, target: str) -> str:
    normalized_target = " ".join(target.strip().lower().split())
    raw = f"{store_id}|{opportunity_type}|{normalized_target}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _persist_opportunity(
    session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID, draft: OpportunityDraft
) -> Opportunity:
    breakdown = compute_priority_score(draft)
    fingerprint = _opportunity_fingerprint(store_id, draft.opportunity_type, draft.fingerprint_target)
    score_breakdown = dataclasses.asdict(breakdown)

    # Beta Readiness Remediation — confirmed second-order bug found during
    # the Round 3 replay: restricting this lookup to status==open meant
    # that once an Opportunity got merged away by consolidate_opportunities
    # (Q2), its fingerprint became permanently unfindable on every later
    # run. A fresh call for the exact same real-world fingerprint then
    # created a brand-new duplicate Opportunity instead of updating the
    # merged one — and the ORIGINAL Recommendation (kept as the dedup
    # survivor, Part R5) stayed pointed at the now-invisible merged
    # Opportunity, so its content (what_we_found etc.) silently stopped
    # being refreshed on every subsequent research run. needs_validation is
    # included too, for the symmetric reason (Section 2/3): a fresh draft
    # for the same fingerprint is exactly the re-validation that should
    # resurrect it. dismissed/expired/actioned are deliberately excluded —
    # those are genuine terminal states where a fresh Opportunity is
    # correct, not a resurrection of an intentionally-closed one.
    existing = session.exec(
        select(Opportunity)
        .where(Opportunity.fingerprint == fingerprint)
        .where(Opportunity.status.in_([OpportunityStatus.open, OpportunityStatus.merged, OpportunityStatus.needs_validation]))  # type: ignore[attr-defined]
    ).first()
    if existing is not None:
        # Refresh everything the draft carries — including affected_*,
        # which are per-run entity IDs (e.g. Intent rows are recreated
        # every research run, never reused) and would otherwise go stale
        # after the very first creation.
        existing.research_run_id = research_run_id
        existing.title = draft.title
        existing.description = draft.description
        existing.affected_intents = draft.affected_intents
        existing.affected_queries = draft.affected_queries
        existing.affected_pages = draft.affected_pages
        existing.affected_products = draft.affected_products
        existing.competitors = draft.competitors
        existing.evidence_ids = draft.evidence_ids
        existing.finding_ids = draft.finding_ids
        existing.google_visibility_gap = draft.google_visibility_gap
        existing.ai_visibility_gap = draft.ai_visibility_gap
        existing.competitor_gap = draft.competitor_gap
        existing.confidence = draft.confidence
        existing.estimated_impact = draft.estimated_impact
        existing.priority_score = breakdown.priority_score
        existing.score_breakdown = score_breakdown
        # Rediscovered this run -> back to open; consolidate_opportunities
        # (called right after every detector has run) independently
        # re-decides merge grouping from scratch each time, so this is
        # never a permanent "un-merge", just "eligible again this round."
        existing.status = OpportunityStatus.open
        existing.merged_into_id = None
        existing.updated_at = utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    opportunity = Opportunity(
        store_id=store_id,
        research_run_id=research_run_id,
        opportunity_type=draft.opportunity_type,
        title=draft.title,
        description=draft.description,
        affected_intents=draft.affected_intents,
        affected_queries=draft.affected_queries,
        affected_pages=draft.affected_pages,
        affected_products=draft.affected_products,
        competitors=draft.competitors,
        evidence_ids=draft.evidence_ids,
        finding_ids=draft.finding_ids,
        google_visibility_gap=draft.google_visibility_gap,
        ai_visibility_gap=draft.ai_visibility_gap,
        competitor_gap=draft.competitor_gap,
        estimated_impact=draft.estimated_impact,
        confidence=draft.confidence,
        effort_estimate=draft.effort_estimate,
        commercial_relevance=draft.commercial_relevance,
        priority_score=breakdown.priority_score,
        score_breakdown=score_breakdown,
        status=OpportunityStatus.open,
        fingerprint=fingerprint,
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)
    return opportunity


def persist_on_demand_opportunity(
    session: Session,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    draft: OpportunityDraft,
    analysis_payload: dict,
) -> Opportunity:
    """Public, deduplicated entry point for a user-requested analysis.

    It deliberately reuses the same fingerprinting, scoring and lifecycle
    rules as detector-created opportunities; the only extra payload is the
    already-persisted comparison used by the dedicated implementation
    template. No second recommendation engine exists for manual actions.
    """
    opportunity = _persist_opportunity(session, store_id, research_run_id, draft)
    opportunity.score_breakdown = {**opportunity.score_breakdown, "analysis": analysis_payload}
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)
    return opportunity


def run_opportunity_discovery_agent(
    session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID
) -> list[Opportunity]:
    """Runs every registered detector (Part E1 — pluggable, not a hardcoded
    list), scores each draft deterministically (Part E2), and persists —
    get-or-create by fingerprint, so re-running research updates an
    existing open Opportunity instead of duplicating it. Detectors are
    free (no AI/network calls), so every discovered opportunity is
    persisted; callers cap how many become Recommendations, not how many
    get discovered."""
    drafts: list[OpportunityDraft] = []
    for detector in OPPORTUNITY_DETECTORS:
        drafts.extend(detector(session, store_id, research_run_id))

    opportunities = [_persist_opportunity(session, store_id, research_run_id, draft) for draft in drafts]
    # Part Q2 — different detectors can independently flag the same
    # underlying intent (e.g. google_visibility_gap + missing_landing_page
    # + ai_citation_gap all firing for one topic); consolidate before
    # returning so callers (recommendation generation, task-impact
    # backfill) only ever see one opportunity per real-world gap.
    return consolidate_opportunities(session, store_id, research_run_id, opportunities)


def run_recommendation_engine(
    session: Session,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    top_opportunities: list[Opportunity],
    max_recommendations: int,
) -> list[Recommendation]:
    """For each of the top-scored Opportunities, builds a Recommendation
    from a deterministic per-type template (Part E3/E4 — never free-form
    AI invention; the LLM plays no role in V1, per the explicit
    requirement that every recommendation is a direct result of
    Research+Evidence+Opportunity). Matches by fingerprint: an existing
    recommendation is updated in place and gets a new RecommendationHistory
    row; nothing is ever silently duplicated or erased (Part E6).

    Also captures the measurement baseline (Group F Part F0) at the exact
    moment a *new* recommendation is created — never for an updated one,
    since a baseline is a one-time 'before' snapshot (Part F0 design
    decision #1).
    """
    recommendations: list[Recommendation] = []

    for opportunity in top_opportunities[:max_recommendations]:
        content = build_recommendation_content(opportunity, session)
        target = opportunity.affected_pages[0] if opportunity.affected_pages else None
        # Keyed off opportunity.id, not affected_intents/affected_pages —
        # those are per-run entity IDs that change every research run.
        # opportunity.id itself is stable across runs because Opportunity
        # is already deduped by a topic-text fingerprint (Part E1), so one
        # real-world opportunity always maps to the same Recommendation.
        fingerprint = hashlib.sha256(f"{store_id}|{opportunity.opportunity_type}|{opportunity.id}".encode("utf-8")).hexdigest()

        # Part R2-F4 — Evidence Scope Integrity: only evidence whose own
        # backing intent/topic actually matches what this opportunity
        # claims to address is allowed onto the recommendation it produces.
        target_topic = target_topic_from_intents(session, opportunity.affected_intents)
        scope = check_evidence_scope(session, target_topic, opportunity.evidence_ids)

        # Beta Readiness Remediation — "NO EVIDENCE → NO RECOMMENDATION",
        # enforced as a general invariant here (not per-detector), so it
        # catches every current and future opportunity_type: a
        # customer-visible Recommendation may never exist with zero
        # supporting evidence. This is the direct fix for Round 3's 6
        # zero-evidence recommendations. The underlying research signal is
        # not discarded — the Opportunity is marked needs_validation so a
        # later run's validate_finding/query_expansion can supply real
        # evidence and re-open the path to a Recommendation.
        # One observation is a lead, not a customer-facing conclusion.
        evidence_supported = len(set(scope.aligned_evidence_ids)) >= 2

        existing = session.exec(
            select(Recommendation)
            .options(defer(Recommendation.page_id), defer(Recommendation.product_id))
            .where(Recommendation.fingerprint == fingerprint)
        ).first()

        if not evidence_supported:
            opportunity.status = OpportunityStatus.needs_validation
            opportunity.updated_at = utcnow()
            session.add(opportunity)

            if existing is not None and existing.status != RecommendationStatus.needs_validation:
                # A previously-supported recommendation lost its evidence on
                # re-scoring (e.g. an upstream merge widened scope and this
                # run's topic-alignment check correctly narrowed it back to
                # nothing) — withdraw it from customer visibility rather
                # than leaving a stale "new" recommendation with no
                # evidence sitting in the store's list.
                existing.status = RecommendationStatus.needs_validation
                existing.evidence_ids = []
                existing.updated_at = utcnow()
                session.add(existing)
                session.add(
                    RecommendationHistory(
                        recommendation_id=existing.id,
                        research_run_id=research_run_id,
                        event_type="evidence_lost_withdrawn",
                        snapshot={"reason": "no evidence survived topic-scope check this run"},
                    )
                )
            session.commit()
            continue

        confidence_result = compute_confidence(session, scope.aligned_evidence_ids, opportunity.finding_ids, opportunity.competitors)

        page_id, product_id = resolve_catalog_targets(
            session, store_id, target, opportunity.affected_products
        )
        if existing is not None:
            # A recommendation that had lost evidence on a prior run and is
            # now re-supported comes back as "new" — real re-validation, not
            # silently resurrected with stale customer-facing text.
            existing.status = RecommendationStatus.new
            existing.last_seen_research_run_id = research_run_id
            existing.confidence = confidence_result.confidence
            existing.confidence_tier = confidence_result.tier
            existing.expected_impact = opportunity.estimated_impact
            existing.priority_score = opportunity.priority_score
            existing.evidence_ids = scope.aligned_evidence_ids
            existing.what_we_found = content.what_we_found
            existing.page_id = page_id
            existing.product_id = product_id
            existing.why_this_improvement = content.why_this_improvement
            existing.claim_basis = content.claim_basis
            existing.updated_at = utcnow()
            session.add(existing)
            session.commit()
            session.refresh(existing)

            session.add(
                RecommendationHistory(
                    recommendation_id=existing.id,
                    research_run_id=research_run_id,
                    event_type="updated",
                    snapshot={"confidence": existing.confidence, "priority_score": existing.priority_score},
                )
            )
            session.commit()
            recommendations.append(existing)
            continue

        recommendation = Recommendation(
            store_id=store_id,
            opportunity_id=opportunity.id,
            first_seen_research_run_id=research_run_id,
            last_seen_research_run_id=research_run_id,
            title=content.title,
            what_we_found=content.what_we_found,
            what_to_do=content.what_to_do,
            why_it_matters=content.why_it_matters,
            why_this_improvement=content.why_this_improvement,
            target_page=target,
            page_id=page_id,
            product_id=product_id,
            target_intents=opportunity.affected_intents,
            evidence_ids=scope.aligned_evidence_ids,
            competitors_reference=opportunity.competitors,
            expected_impact=opportunity.estimated_impact,
            confidence=confidence_result.confidence,
            confidence_tier=confidence_result.tier,
            claim_basis=content.claim_basis,
            effort_estimate=opportunity.effort_estimate,
            priority_score=opportunity.priority_score,
            implementation_steps=content.implementation_steps,
            measurement_plan=content.measurement_plan,
            implementation_package=content.implementation_package,
            status=RecommendationStatus.new,
            fingerprint=fingerprint,
        )
        session.add(recommendation)
        session.commit()
        session.refresh(recommendation)

        session.add(
            RecommendationHistory(
                recommendation_id=recommendation.id,
                research_run_id=research_run_id,
                event_type="created",
                snapshot={"confidence": recommendation.confidence, "priority_score": recommendation.priority_score},
            )
        )
        session.commit()

        capture_measurement_baseline(session, recommendation, research_run_id)

        recommendations.append(recommendation)

    # Part R5 — semantic dedup runs across the store's whole active set
    # (not just this run's touched recommendations), so it also collapses
    # duplicate pairs that were created across two different research runs,
    # or before this fix existed at all.
    consolidate_duplicate_recommendations(session, store_id, research_run_id)

    # Beta Readiness Remediation — same "whole active set, not just this
    # run's touched rows" reasoning as the dedup sweep above: a
    # Recommendation whose Opportunity no longer gets rediscovered this run
    # (e.g. the intent simply wasn't re-queried) is never revisited by the
    # per-opportunity loop above, so a legacy zero-evidence recommendation
    # from before this invariant existed (Round 3's confirmed 6-of-38 case)
    # would otherwise sit untouched forever. Sweep the whole store so "NO
    # EVIDENCE -> NO RECOMMENDATION" is actually store-wide and permanent,
    # not just enforced going forward for opportunities that happen to be
    # reprocessed.
    withdraw_unsupported_recommendations(session, store_id, research_run_id)

    return recommendations


def withdraw_unsupported_recommendations(session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID) -> int:
    """Store-wide sweep: any customer-visible Recommendation with empty
    evidence_ids is withdrawn to needs_validation, regardless of whether its
    Opportunity was touched by this run's detectors. Returns the count
    withdrawn. Idempotent — a recommendation already in needs_validation is
    left alone (it may still legitimately hold stale evidence_ids from
    before it was withdrawn; re-checking it here would be redundant with
    the per-opportunity loop, which already handles re-validation when the
    Opportunity IS rediscovered)."""
    stale = session.exec(
        select(Recommendation)
        .options(defer(Recommendation.page_id), defer(Recommendation.product_id))
        .where(Recommendation.store_id == store_id)
        .where(Recommendation.status != RecommendationStatus.needs_validation)
    ).all()
    withdrawn = 0
    for rec in stale:
        if rec.evidence_ids:
            continue
        rec.status = RecommendationStatus.needs_validation
        rec.updated_at = utcnow()
        session.add(rec)
        session.add(
            RecommendationHistory(
                recommendation_id=rec.id,
                research_run_id=research_run_id,
                event_type="evidence_lost_withdrawn",
                snapshot={"reason": "store-wide sweep found zero evidence_ids on a customer-visible recommendation"},
            )
        )
        opportunity = session.get(Opportunity, rec.opportunity_id)
        if opportunity is not None and opportunity.status == OpportunityStatus.open:
            opportunity.status = OpportunityStatus.needs_validation
            opportunity.updated_at = utcnow()
            session.add(opportunity)
        withdrawn += 1
    session.commit()
    return withdrawn
