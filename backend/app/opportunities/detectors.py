import uuid
from dataclasses import dataclass, field
from typing import Callable

from sqlmodel import Session, select

from app.competitors.classification import is_business_competitor
from app.models.ai_visibility import AIVisibilityObservation
from app.models.competitor import Competitor, CompetitorRelationship, RelationshipSource
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.finding import Finding
from app.models.intent import Intent
from app.models.page_intelligence import PageGapAnalysis
from app.models.serp import SerpObservation

WEAK_RANK_THRESHOLD = 10
MIN_INTENT_CONFIDENCE = 0.4
MIN_CATEGORY_INTENTS = 2
CATEGORY_COVERAGE_FLOOR = 0.34


@dataclass
class OpportunityDraft:
    """What a detector produces — the engine (Part E1's
    run_opportunity_discovery_agent, plus Part E2 scoring) turns this into
    a persisted Opportunity row. Kept separate from the Opportunity model
    itself so detectors never touch the session directly — pure functions,
    easy to unit test."""

    opportunity_type: str
    title: str
    description: str
    fingerprint_target: str  # combined with store_id+opportunity_type to form the dedup fingerprint
    affected_intents: list[str] = field(default_factory=list)
    affected_queries: list[str] = field(default_factory=list)
    affected_pages: list[str] = field(default_factory=list)
    affected_products: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    finding_ids: list[str] = field(default_factory=list)
    google_visibility_gap: float = 0.0
    ai_visibility_gap: float = 0.0
    competitor_gap: float = 0.0
    estimated_impact: float = 0.0
    confidence: float = 0.0
    effort_estimate: str = "medium"
    commercial_relevance: float = 0.0


def _serp_observations_by_intent(session: Session, research_run_id: uuid.UUID) -> dict[uuid.UUID, SerpObservation]:
    observations = session.exec(
        select(SerpObservation).where(SerpObservation.research_run_id == research_run_id)
    ).all()
    return {obs.intent_id: obs for obs in observations}


def _evidence_ids_for(session: Session, source_type: EvidenceSourceType, source_id: uuid.UUID) -> list[str]:
    rows = session.exec(
        select(Evidence).where(Evidence.source_type == source_type).where(Evidence.source_id == source_id)
    ).all()
    return [str(r.id) for r in rows]


def _finding_ids_for_competitor(session: Session, research_run_id: uuid.UUID, competitor_id: uuid.UUID) -> list[str]:
    findings = session.exec(select(Finding).where(Finding.research_run_id == research_run_id)).all()
    return [str(f.id) for f in findings if str(competitor_id) in f.affected_competitors]


def detect_missing_landing_page_opportunities(
    session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID
) -> list[OpportunityDraft]:
    """From PageGapAnalysis (Group D3) — a competitor demonstrably covers
    content for an intent we don't. This is the strongest-evidence
    detector: it's already a crawled, AI-compared, evidence-backed gap."""
    analyses = session.exec(
        select(PageGapAnalysis).where(PageGapAnalysis.research_run_id == research_run_id)
    ).all()

    drafts: list[OpportunityDraft] = []
    for analysis in analyses:
        intent = session.get(Intent, analysis.intent_id)
        if intent is None:
            continue

        # Part Q3 — a marketplace/social/gov domain winning the SERP slot
        # is not a real business competitor (Part G-B2); telling a store
        # owner "you're losing to X" when X isn't a real competitor is
        # exactly the "irrelevant competitors" failure mode to avoid.
        competitor = session.get(Competitor, analysis.competitor_id)
        if competitor is None or not is_business_competitor(competitor):
            continue

        evidence_ids = _evidence_ids_for(session, EvidenceSourceType.page_gap_analysis, analysis.id)
        finding_ids = _finding_ids_for_competitor(session, research_run_id, analysis.competitor_id)

        drafts.append(
            OpportunityDraft(
                opportunity_type="missing_landing_page",
                title=f"غطِّ نية '{intent.topic}' بصفحة مخصصة",
                description=analysis.recommendation_summary,
                fingerprint_target=intent.topic,
                affected_intents=[str(intent.stable_intent_id)],
                competitors=[str(analysis.competitor_id)],
                evidence_ids=evidence_ids,
                finding_ids=finding_ids,
                competitor_gap=1.0,
                google_visibility_gap=1.0,
                estimated_impact=analysis.confidence or 0.5,
                confidence=analysis.confidence or 0.5,
                effort_estimate="medium",
                commercial_relevance=intent.confidence,
            )
        )
    return drafts


def detect_google_visibility_gap_opportunities(
    session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID
) -> list[OpportunityDraft]:
    """Intents worth caring about (confidence above the floor) where the
    store is absent or weak in Google results. Quality-rejected intents
    (Part G-B1) never generate an opportunity."""
    intents = session.exec(
        select(Intent).where(Intent.research_run_id == research_run_id).where(Intent.is_accepted == True)  # noqa: E712
    ).all()
    observations_by_intent = _serp_observations_by_intent(session, research_run_id)

    drafts: list[OpportunityDraft] = []
    for intent in intents:
        if intent.confidence < MIN_INTENT_CONFIDENCE:
            continue
        observation = observations_by_intent.get(intent.id)

        # Beta Readiness Remediation (Round 3 P0): "no SerpObservation this
        # run" is NOT evidence of weak/absent visibility — it means the
        # intent was simply never queried (beyond serp_max_queries_per_run,
        # no primary keyword, or an errored SearchProvider call). Treating
        # the two as equivalent is exactly the bug that produced Round 3's
        # 6 zero-evidence recommendations (all google_visibility_gap): the
        # detector asserted "المتجر غير ظاهر ضمن أفضل 10 نتيجة" — a claim —
        # with evidence_ids=[] backing it. We only ever assert a visibility
        # claim when we actually queried Google for this intent: a real
        # SerpObservation row exists (client_rank may itself be None,
        # meaning "queried and not found in the top results" — that IS a
        # supported claim, with a real Evidence row behind it). No
        # observation at all => no claim, no opportunity, full stop.
        if observation is None:
            continue

        rank = observation.client_rank
        if rank is not None and rank <= WEAK_RANK_THRESHOLD:
            continue

        # The SerpObservation itself is the evidence — guaranteed non-empty
        # now that we only reach here when observation is not None.
        evidence_ids = _evidence_ids_for(session, EvidenceSourceType.serp_observation, observation.id)

        gap = 1.0 if rank is None else min(1.0, rank / 50)
        drafts.append(
            OpportunityDraft(
                opportunity_type="google_visibility_gap",
                title=f"حسّن ظهورك في Google لنية '{intent.topic}'",
                description=(
                    f"المتجر غير ظاهر ضمن أفضل {WEAK_RANK_THRESHOLD} نتيجة لهذه النية"
                    if rank is None
                    else f"المتجر يظهر بترتيب ضعيف ({rank}) لهذه النية"
                ),
                fingerprint_target=intent.topic,
                affected_intents=[str(intent.stable_intent_id)],
                evidence_ids=evidence_ids,
                google_visibility_gap=gap,
                estimated_impact=intent.confidence,
                confidence=0.6,
                effort_estimate="medium",
                commercial_relevance=intent.confidence,
            )
        )
    return drafts


def detect_ai_citation_gap_opportunities(
    session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID
) -> list[OpportunityDraft]:
    """Intents where AI assistants never mention the store, but a
    competitor was cited for the same intent this run — real evidence of
    both the gap and that AI answers this question at all."""
    observations = session.exec(
        select(AIVisibilityObservation).where(AIVisibilityObservation.research_run_id == research_run_id)
    ).all()
    by_intent: dict[uuid.UUID, list[AIVisibilityObservation]] = {}
    for obs in observations:
        by_intent.setdefault(obs.intent_id, []).append(obs)

    ai_competitor_relationships = session.exec(
        select(CompetitorRelationship)
        .where(CompetitorRelationship.research_run_id == research_run_id)
        .where(CompetitorRelationship.source == RelationshipSource.ai_visibility)
    ).all()
    competitors_by_intent: dict[uuid.UUID, set[uuid.UUID]] = {}
    for rel in ai_competitor_relationships:
        competitors_by_intent.setdefault(rel.intent_id, set()).add(rel.competitor_id)

    drafts: list[OpportunityDraft] = []
    for intent_id, obs_list in by_intent.items():
        if any(o.mentioned for o in obs_list):
            continue
        raw_competitor_ids = competitors_by_intent.get(intent_id)
        if not raw_competitor_ids:
            continue

        # Part Q3 — same "irrelevant competitors" filter as
        # detect_missing_landing_page_opportunities: an AI answer citing a
        # marketplace/directory alongside (or instead of) real competitors
        # must never surface as "you're losing to X" when X isn't a real
        # business competitor.
        competitors = [session.get(Competitor, cid) for cid in raw_competitor_ids]
        competitor_ids = {c.id for c in competitors if c is not None and is_business_competitor(c)}
        if not competitor_ids:
            continue

        intent = session.get(Intent, intent_id)
        if intent is None:
            continue

        evidence_ids = [
            eid
            for obs in obs_list
            for eid in _evidence_ids_for(session, EvidenceSourceType.ai_visibility_observation, obs.id)
        ]

        drafts.append(
            OpportunityDraft(
                opportunity_type="ai_citation_gap",
                title=f"اجعل متجرك يُذكر في إجابات AI عن '{intent.topic}'",
                description=f"لم يُذكر المتجر في {len(obs_list)} محاولة، بينما ذُكر {len(competitor_ids)} منافس لنفس النية",
                fingerprint_target=intent.topic,
                affected_intents=[str(intent.stable_intent_id)],
                competitors=[str(c) for c in competitor_ids],
                evidence_ids=evidence_ids,
                ai_visibility_gap=1.0,
                competitor_gap=0.6,
                estimated_impact=intent.confidence,
                confidence=0.55,
                effort_estimate="medium",
                commercial_relevance=intent.confidence,
            )
        )
    return drafts


def detect_category_visibility_gap_opportunities(
    session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID
) -> list[OpportunityDraft]:
    """Category-level view (Intent.category as the practical stand-in for
    a query cluster — no clustering system exists in the project, and we
    won't build one now) — flags whole categories where visibility is
    uniformly weak, not just single intents. Quality-rejected intents
    (Part G-B1) never generate an opportunity."""
    intents = session.exec(
        select(Intent).where(Intent.research_run_id == research_run_id).where(Intent.is_accepted == True)  # noqa: E712
    ).all()
    observations_by_intent = _serp_observations_by_intent(session, research_run_id)

    by_category: dict[str, list[Intent]] = {}
    for intent in intents:
        if intent.category:
            by_category.setdefault(intent.category, []).append(intent)

    drafts: list[OpportunityDraft] = []
    for category, category_intents in by_category.items():
        # Beta Readiness Remediation (Round 3 P0): same "no observation !=
        # confirmed weak" error as google_visibility_gap above, but at
        # category granularity — an intent never queried this run must not
        # be counted as "not visible" in the coverage denominator, or the
        # claim ("N of M intents visible") overstates how much was actually
        # measured. Only intents with a real SerpObservation count toward
        # M; an unmeasured intent is simply excluded from the aggregate,
        # not silently treated as a negative data point.
        measured = [i for i in category_intents if observations_by_intent.get(i.id) is not None]
        if len(measured) < MIN_CATEGORY_INTENTS:
            continue
        ranks = {i.id: observations_by_intent[i.id].client_rank for i in measured}
        visible = sum(1 for r in ranks.values() if r is not None and r <= WEAK_RANK_THRESHOLD)
        coverage = visible / len(measured)
        if coverage >= CATEGORY_COVERAGE_FLOOR:
            continue

        # Every SerpObservation behind this category's *measured* intents is
        # evidence for the aggregate claim — guaranteed non-empty since
        # `measured` only contains intents with a real observation.
        evidence_ids: list[str] = []
        for i in measured:
            evidence_ids.extend(
                _evidence_ids_for(session, EvidenceSourceType.serp_observation, observations_by_intent[i.id].id)
            )

        avg_confidence = sum(i.confidence for i in measured) / len(measured)
        drafts.append(
            OpportunityDraft(
                opportunity_type="category_visibility_gap",
                title=f"تصنيف '{category}' ضعيف الظهور ككل",
                description=(
                    f"{visible} من {len(measured)} نية (المُقاسة فعليًا) ظاهرة فقط ضمن أفضل "
                    f"{WEAK_RANK_THRESHOLD} نتيجة في هذا التصنيف"
                ),
                fingerprint_target=category,
                affected_intents=[str(i.stable_intent_id) for i in measured],
                evidence_ids=evidence_ids,
                google_visibility_gap=1.0 - coverage,
                estimated_impact=avg_confidence,
                confidence=0.5,
                effort_estimate="high",
                commercial_relevance=avg_confidence,
            )
        )
    return drafts


OPPORTUNITY_DETECTORS: list[Callable[[Session, uuid.UUID, uuid.UUID], list[OpportunityDraft]]] = [
    detect_missing_landing_page_opportunities,
    detect_google_visibility_gap_opportunities,
    detect_ai_citation_gap_opportunities,
    detect_category_visibility_gap_opportunities,
]
"""Registry, not a hardcoded closed list (Group E design decision #3) — add
a new detector function elsewhere and append it here; nothing else in the
engine (Part E1's run_opportunity_discovery_agent) needs to change."""
