import uuid

from sqlmodel import Session, select

from app.competitors.market_map import compute_competitor_rankings
from app.models.competitor import CompetitorRelationship, RelationshipSource
from app.models.finding import Finding
from app.models.opportunity import Opportunity
from app.models.research_task import ResearchTask
from app.research.finding_validation import record_evidence_check

DOMINANT_COMPETITOR_MIN_APPEARANCES = 3
DOMINANT_COMPETITOR_MAX_AVG_RANK = 3.0


def extract_findings_from_market_map(
    session: Session,
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    origin_task_id: uuid.UUID | None = None,
) -> list[Finding]:
    """Deterministic rule-based extraction — never AI (same 'AI is not
    Source of Truth' principle as the rest of the project). A competitor
    that appears strongly across enough intents becomes a hypothesis
    Finding; independent validate_finding/validate_cross_surface_finding
    checks (Part G-B3) are what can raise it to `validated`, not this
    function.

    Part G-B2 tie-in: only competitors already classified direct_competitor
    (app.competitors.classification, which has already run by the time this
    is called — see MARKET_MAP_MOVING_TASK_TYPES in research/loop.py)
    become findings. A 'dominant competitor' claim about YouTube or a
    marketplace was exactly the noise G-A flagged — those domains are real
    SERP entities worth knowing about, just not worth a competitive
    finding.
    """
    existing_competitor_ids = {
        cid
        for finding in session.exec(select(Finding).where(Finding.research_run_id == research_run_id)).all()
        for cid in finding.affected_competitors
    }

    rankings = compute_competitor_rankings(session, research_run_id)
    findings: list[Finding] = []

    for ranking in rankings:
        if str(ranking.competitor_id) in existing_competitor_ids:
            continue
        if ranking.classification != "direct_competitor":
            continue
        if ranking.serp_appearances < DOMINANT_COMPETITOR_MIN_APPEARANCES:
            continue
        if ranking.avg_serp_rank is None or ranking.avg_serp_rank > DOMINANT_COMPETITOR_MAX_AVG_RANK:
            continue

        serp_relationships = session.exec(
            select(CompetitorRelationship)
            .where(CompetitorRelationship.research_run_id == research_run_id)
            .where(CompetitorRelationship.competitor_id == ranking.competitor_id)
            .where(CompetitorRelationship.source == RelationshipSource.serp)
        ).all()
        affected_intents = sorted({str(r.intent_id) for r in serp_relationships})

        finding = Finding(
            store_id=store_id,
            research_run_id=research_run_id,
            finding_type="dominant_competitor",
            statement=(
                f"{ranking.domain} يظهر بقوة عبر {ranking.serp_appearances} استعلام "
                f"بمتوسط ترتيب {ranking.avg_serp_rank:.1f}"
            ),
            affected_competitors=[str(ranking.competitor_id)],
            affected_intents=affected_intents,
            origin_task_id=origin_task_id,
        )
        # Part G-B3 — the market-map signal that created this finding IS
        # the first evidence source ("store"), recorded explicitly instead
        # of an unexplained confidence=0.5 default.
        record_evidence_check(
            finding,
            source="store",
            supports=True,
            detail=(
                f"مصنَّف كـ direct_competitor، ظهر في {ranking.serp_appearances} استعلام SERP "
                f"بمتوسط ترتيب {ranking.avg_serp_rank:.1f}"
            ),
        )
        session.add(finding)
        session.commit()
        session.refresh(finding)
        findings.append(finding)

    return findings


def backfill_task_opportunity_impact(session: Session, research_run_id: uuid.UUID, opportunities: list[Opportunity]) -> None:
    """Part G-B4 — a research_task's `affected_opportunities_count` can only
    be known once Opportunities exist, which happens in a later agent_run
    (opportunity_recommendation_agent_run), well after every research_task
    row from the iterative loop is already `completed`. Called once from
    there: walks Opportunity.finding_ids -> Finding.origin_task_id and
    updates the originating tasks. Opportunities with no finding_ids (most
    detectors don't derive from Finding at all — Part E1) simply contribute
    nothing, which is the honest answer, not a bug."""
    finding_id_hits: dict[str, int] = {}
    for opportunity in opportunities:
        for finding_id in opportunity.finding_ids:
            finding_id_hits[finding_id] = finding_id_hits.get(finding_id, 0) + 1
    if not finding_id_hits:
        return

    findings = session.exec(
        select(Finding).where(Finding.id.in_([uuid.UUID(fid) for fid in finding_id_hits]))
    ).all()

    task_hits: dict[uuid.UUID, int] = {}
    for finding in findings:
        if finding.origin_task_id is None:
            continue
        task_hits[finding.origin_task_id] = task_hits.get(finding.origin_task_id, 0) + finding_id_hits.get(
            str(finding.id), 0
        )

    for task_id, count in task_hits.items():
        task = session.get(ResearchTask, task_id)
        if task is not None and task.research_run_id == research_run_id:
            task.affected_opportunities_count = count
            session.add(task)
    if task_hits:
        session.commit()
