import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import defer
from sqlmodel import Session, select

from app.api.schemas import (
    CompetitorReferenceItem,
    EvidenceItem,
    ImplementationPackageResponse,
    OpportunityItem,
    RecommendationDetail,
    RecommendationEvidenceResponse,
    RecommendationFindingItem,
    SaveImplementationDraftRequest,
    UpdateRecommendationStatusRequest,
)
from app.schemas.implementation_execution import GenerateImplementationRequest
from app.schemas.on_demand_job import OnDemandJobResponse
from app.competitors.classification import is_business_competitor
from app.core.config import get_settings
from app.core.db import get_session
from app.models.base import utcnow
from app.models.competitor import Competitor
from app.models.opportunity import Opportunity
from app.models.recommendation import Recommendation, RecommendationHistory, RecommendationStatus
from app.models.research import AgentRun, ResearchRun, ResearchRunType, RunStatus
from app.workers.tasks import execute_implementation_generation_task
from app.opportunities.evidence_trace import trace_recommendation_evidence
from app.opportunities.freshness import (
    latest_completed_research_run_id,
    recommendation_freshness,
    select_primary_recommendations,
)


def _resolve_competitor_references(session: Session, competitor_ids: list[str]) -> list[CompetitorReferenceItem]:
    """Part R6 — Recommendation.competitors_reference only ever stored raw
    competitor UUIDs (see recommendation_engine.py); resolving them here
    means the UI never has to show a bare ID, and can frame a referenced
    competitor by what it actually is (a real business rival vs. a
    publisher/marketplace/etc. entity that merely appeared in the evidence)."""
    items: list[CompetitorReferenceItem] = []
    for raw_id in competitor_ids:
        try:
            competitor = session.get(Competitor, uuid.UUID(raw_id))
        except ValueError:
            continue
        if competitor is None:
            continue
        items.append(
            CompetitorReferenceItem(
                id=competitor.id,
                domain=competitor.domain,
                name=competitor.name,
                classification=competitor.classification,
                is_business_competitor=is_business_competitor(competitor),
            )
        )
    return items

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _get_recommendation_legacy_compatible(session: Session, recommendation_id: uuid.UUID) -> Recommendation | None:
    """Read rows without requiring optional relation columns added later."""
    return session.exec(
        select(Recommendation)
        .options(defer(Recommendation.page_id), defer(Recommendation.product_id))
        .where(Recommendation.id == recommendation_id)
    ).first()


def _to_detail(session: Session, r: Recommendation) -> RecommendationDetail:
    opportunity = session.get(Opportunity, r.opportunity_id)
    settings = get_settings()
    latest_run_id = latest_completed_research_run_id(session, r.store_id)
    primary_ids = {p.id for p in select_primary_recommendations(session, r.store_id, settings.recommendation_primary_queue_size)}
    return RecommendationDetail(
        id=r.id,
        opportunity_id=r.opportunity_id,
        opportunity_type=opportunity.opportunity_type if opportunity else "",
        title=r.title,
        what_we_found=r.what_we_found,
        what_to_do=r.what_to_do,
        why_it_matters=r.why_it_matters,
        why_this_improvement=r.why_this_improvement,
        target_page=r.target_page,
        target_intents=r.target_intents,
        expected_impact=r.expected_impact,
        confidence=r.confidence,
        confidence_tier=r.confidence_tier,
        claim_basis=r.claim_basis,
        effort_estimate=r.effort_estimate,
        priority_score=r.priority_score,
        status=r.status.value,
        is_primary=r.id in primary_ids,
        freshness=recommendation_freshness(r, latest_run_id),
        implementation_url=r.implementation_url,
        implemented_at=r.implemented_at.isoformat() if r.implemented_at else None,
        implementation_steps=r.implementation_steps,
        measurement_plan=r.measurement_plan,
        evidence_ids=r.evidence_ids,
        competitors_reference=_resolve_competitor_references(session, r.competitors_reference),
    )


@router.get("/{recommendation_id}", response_model=RecommendationDetail)
def get_recommendation(recommendation_id: uuid.UUID, session: Session = Depends(get_session)) -> RecommendationDetail:
    recommendation = _get_recommendation_legacy_compatible(session, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return _to_detail(session, recommendation)


@router.patch("/{recommendation_id}/status", response_model=RecommendationDetail)
def update_recommendation_status(
    recommendation_id: uuid.UUID,
    payload: UpdateRecommendationStatusRequest,
    session: Session = Depends(get_session),
) -> RecommendationDetail:
    recommendation = _get_recommendation_legacy_compatible(session, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="recommendation not found")

    try:
        new_status = RecommendationStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid status '{payload.status}'")

    previous_status = recommendation.status
    recommendation.status = new_status
    if payload.implementation_url:
        recommendation.implementation_url = payload.implementation_url
    if new_status == RecommendationStatus.implemented and recommendation.implemented_at is None:
        recommendation.implemented_at = utcnow()
    recommendation.updated_at = utcnow()
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)

    latest_run = session.exec(
        select(ResearchRun)
        .where(ResearchRun.store_id == recommendation.store_id)
        .order_by(ResearchRun.created_at.desc())  # type: ignore[arg-type]
    ).first()

    session.add(
        RecommendationHistory(
            recommendation_id=recommendation.id,
            research_run_id=(latest_run.id if latest_run else recommendation.first_seen_research_run_id),
            event_type="status_changed",
            snapshot={
                "previous_status": previous_status.value,
                "new_status": new_status.value,
                "implementation_url": recommendation.implementation_url,
            },
        )
    )
    session.commit()

    return _to_detail(session, recommendation)


@router.get("/{recommendation_id}/evidence", response_model=RecommendationEvidenceResponse)
def get_recommendation_evidence(
    recommendation_id: uuid.UUID, session: Session = Depends(get_session)
) -> RecommendationEvidenceResponse:
    trace = trace_recommendation_evidence(session, recommendation_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="recommendation not found")

    opportunity = trace["opportunity"]
    return RecommendationEvidenceResponse(
        opportunity=(
            OpportunityItem(
                id=opportunity.id,
                opportunity_type=opportunity.opportunity_type,
                title=opportunity.title,
                description=opportunity.description,
                priority_score=opportunity.priority_score,
                score_breakdown=opportunity.score_breakdown,
                confidence=opportunity.confidence,
                effort_estimate=opportunity.effort_estimate,
                status=opportunity.status.value,
                affected_intents=opportunity.affected_intents,
                competitors=opportunity.competitors,
            )
            if opportunity
            else None
        ),
        findings=[
            RecommendationFindingItem(
                id=f.id, finding_type=f.finding_type, statement=f.statement, confidence=f.confidence,
                status=f.status.value,
            )
            for f in trace["findings"]
        ],
        evidence=[
            EvidenceItem(id=e.id, source_type=e.source_type.value, confidence=e.confidence, summary=e.summary)
            for e in trace["evidence"]
        ],
    )


@router.get("/{recommendation_id}/implementation-package", response_model=ImplementationPackageResponse)
def get_implementation_package(
    recommendation_id: uuid.UUID, session: Session = Depends(get_session)
) -> ImplementationPackageResponse:
    recommendation = _get_recommendation_legacy_compatible(session, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return ImplementationPackageResponse(implementation_package=recommendation.implementation_package)


@router.patch("/{recommendation_id}/implementation-draft", response_model=ImplementationPackageResponse)
def save_implementation_draft(
    recommendation_id: uuid.UUID,
    payload: SaveImplementationDraftRequest,
    session: Session = Depends(get_session),
) -> ImplementationPackageResponse:
    recommendation = _get_recommendation_legacy_compatible(session, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="recommendation not found")

    allowed = {
        "title", "meta_description", "h1", "description", "features", "usage",
        "specifications", "image_alt", "h2", "faq", "internal_links", "instructions",
    }
    raw_faq = payload.fields.get("faq")
    if isinstance(raw_faq, list):
        for item in raw_faq:
            if not isinstance(item, dict):
                continue
            answer = item.get("answer")
            supported = bool(item.get("source")) or item.get("confirmed") is True
            if isinstance(answer, str) and answer.strip() and not supported:
                raise HTTPException(status_code=422, detail="each FAQ answer must carry a source or explicit merchant confirmation")
    draft: dict = {}
    for key, value in payload.fields.items():
        if key not in allowed:
            continue
        if isinstance(value, str):
            draft[key] = value.strip()
        elif isinstance(value, list):
            cleaned = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    cleaned.append(item.strip())
                elif isinstance(item, dict):
                    normalized: dict = {
                        str(item_key): item_value.strip()
                        for item_key, item_value in item.items()
                        if isinstance(item_value, str) and item_value.strip()
                    }
                    if item.get("confirmed") is True:
                        normalized["confirmed"] = True
                    if normalized:
                        cleaned.append(normalized)
            draft[key] = cleaned
        elif isinstance(value, dict):
            draft[key] = {
                str(item_key): item_value.strip()
                for item_key, item_value in value.items()
                if isinstance(item_value, str) and item_value.strip()
            }

    package = dict(recommendation.implementation_package or {})
    package["user_draft"] = draft
    recommendation.implementation_package = package
    recommendation.status = RecommendationStatus.planned
    recommendation.updated_at = utcnow()
    session.add(recommendation)
    session.add(RecommendationHistory(
        recommendation_id=recommendation.id,
        research_run_id=recommendation.last_seen_research_run_id,
        event_type="implementation_draft_saved",
        snapshot={"fields": sorted(draft)},
    ))
    session.commit()
    return ImplementationPackageResponse(implementation_package=package)


@router.post("/{recommendation_id}/generate-implementation", response_model=OnDemandJobResponse, status_code=status.HTTP_202_ACCEPTED)
def generate_implementation(
    recommendation_id: uuid.UUID,
    payload: GenerateImplementationRequest,
    session: Session = Depends(get_session),
) -> OnDemandJobResponse:
    recommendation = _get_recommendation_legacy_compatible(session, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    if not recommendation.evidence_ids:
        raise HTTPException(status_code=409, detail="recommendation has no evidence and cannot generate implementation")

    run = ResearchRun(store_id=recommendation.store_id, run_type=ResearchRunType.discovery, status=RunStatus.pending)
    session.add(run); session.commit(); session.refresh(run)
    agent = AgentRun(
        research_run_id=run.id, agent_type="on_demand_implementation_generation", status=RunStatus.pending,
        findings={"request": {"recommendation_id": str(recommendation.id), "mode": payload.mode}, "topic": f"تنفيذ التوصية: {recommendation.title}"},
    )
    session.add(agent); session.commit()
    execute_implementation_generation_task.delay(str(recommendation.store_id), str(run.id))
    return OnDemandJobResponse(research_run_id=str(run.id), kind="implementation_generation", status="pending")
