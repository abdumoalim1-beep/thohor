import uuid
from datetime import datetime, timezone
from html import unescape
from urllib.parse import unquote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import defer
from sqlmodel import Session, func, select

from app.ai_visibility.cross_surface import compute_cross_surface_visibility
from app.ai_visibility.metrics import (
    compute_ai_visibility_metrics,
    compute_ai_visibility_metrics_by_surface,
)
from app.ai_visibility.surfaces import AI_VISIBILITY_SURFACES, unavailable_surface_names
from app.api.schemas import (
    AgentRunSummary,
    AIVisibilityListResponse,
    AIVisibilityObservationItem,
    AIVisibilitySummary,
    AlertItem,
    AlertListResponse,
    BrandItem,
    BrandNameConfirmRequest,
    BrandNameConfirmResponse,
    CancelResearchRunResponse,
    CapturePageScreenshotRequest,
    CapturePageScreenshotResponse,
    CategoryWorkspaceItem,
    CategoryWorkspaceListResponse,
    ComponentSnapshotItem,
    CompetitorConfirmationRequest,
    CompetitorListItem,
    CompetitorListResponse,
    CostSummaryResponse,
    CreateStoreRequest,
    CreateStoreResponse,
    CrossSurfaceIntentItem,
    CrossSurfaceVisibilityResponse,
    FindingItem,
    FindingListResponse,
    IntentClusterItem,
    IntentClusterListResponse,
    IntentKeywordItem,
    IntentListItem,
    IntentListResponse,
    OnboardingCompetitorSummary,
    OnboardingLeadRequest,
    OnboardingLeadResponse,
    OnboardingSampleIntent,
    OnboardingStageMetric,
    OnboardingSummaryResponse,
    OpportunityItem,
    OpportunityListResponse,
    OptimizeProductImageRequest,
    OptimizeProductImageResponse,
    PageWorkspaceItem,
    PageWorkspaceListResponse,
    PageWorkspaceResponse,
    PageGapItem,
    PageGapListResponse,
    ProductPageCheckItem,
    ProductImageInsightItem,
    ProductWorkspaceItem,
    ProductWorkspaceListResponse,
    ProductWorkspaceRecommendationItem,
    ProductWorkspaceResponse,
    ProductSampleItem,
    RecommendationItem,
    RecommendationListResponse,
    ResearchRunSummary,
    ResearchSummary,
    ResearchTaskItem,
    ResearchTaskListResponse,
    StoreDetailResponse,
    StoreFeedbackRequest,
    StoreFeedbackResponse,
    StoreUnderstandingResponse,
    SuggestedCompetitorItem,
    SurfaceMetrics,
    SurfaceUsageItem,
    TopCategoryItem,
    VisibilitySummary,
)
from app.api.store_profile import build_store_profile
from app.analysis.snapshots import latest_component_snapshots
from app.competitors.market_map import compute_competitor_rankings
from app.core.config import get_settings
from app.core.db import get_session
from app.core.storage import get_storage
from app.crawler.store_intelligence import _guess_brand_name_from_domain
from app.models.ai_execution import AIExecution
from app.models.ai_visibility import AIVisibilityObservation, PromptVariant
from app.models.alert import Alert
from app.models.catalog import Brand, Category, Page, Product
from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.finding import Finding
from app.models.intent import Intent, IntentKeyword, Keyword
from app.models.intent_cluster import IntentCluster
from app.models.observation import PageObservation
from app.models.onboarding_lead import OnboardingLead
from app.models.opportunity import Opportunity
from app.models.org import Organization
from app.models.page_intelligence import PageGapAnalysis
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import AgentRun, ResearchRun, ResearchRunType, RunStatus
from app.models.research_task import ResearchTask
from app.models.serp import SerpExecution, SerpObservation
from app.models.store import Store
from app.models.store_feedback import StoreFeedback
from app.opportunities.detectors import OpportunityDraft
from app.opportunities.freshness import (
    latest_completed_research_run_id,
    recommendation_freshness,
    select_primary_recommendations,
)
from app.store_intelligence.brand_name_resolution import registered_hostname, resolve_best_available_name
from app.store_intelligence.catalog_resolution import canonical_store_url
from app.opportunities.recommendation_engine import (
    persist_on_demand_opportunity,
    run_recommendation_engine,
)
from app.orchestrator.research_orchestrator import ResearchOrchestrator
from app.providers.search.pricing import estimate_search_cost_usd
from app.research.cancellation import request_run_cancellation
from app.research.cost_summary import compute_cost_summary
from app.research.market_exploration import store_domain
from app.schemas.market_exploration import (
    MarketExplorationEstimate,
    MarketExplorationRequest,
    MarketExplorationResponse,
    MarketExplorationResultItem,
)
from app.schemas.on_demand_history import (
    OnDemandAnalysisHistoryItem,
    OnDemandAnalysisHistoryResponse,
)
from app.schemas.on_demand_job import OnDemandJobResponse, OnDemandJobStatus
from app.schemas.winning_page_analysis import (
    ConvertWinningPageAnalysisResponse,
    WinningPageAnalysisOutput,
    WinningPageAnalysisRequest,
    WinningPageAnalysisResponse,
)
from app.serp.metrics import compute_visibility_metrics
from app.store_intelligence.understanding import (
    build_business_info,
    build_category_previews,
    resolve_understanding_stage,
)
from app.store_intelligence.product_workspace import (
    analyze_product_images,
    completion_score,
    extract_product_description,
    implementation_fields,
    product_page_checks,
    general_page_checks,
)
from app.store_intelligence.image_optimizer import download_and_optimize_image
from app.store_intelligence.page_screenshot import capture_page_screenshot
from app.workers.tasks import (
    execute_market_exploration_task,
    execute_research_run_task,
    execute_winning_page_analysis_task,
)

router = APIRouter(prefix="/stores", tags=["stores"])


def _latest_pipeline_run(session: Session, store_id: uuid.UUID) -> ResearchRun | None:
    """Return the latest full store pipeline, excluding on-demand discovery jobs."""
    return session.exec(
        select(ResearchRun)
        .where(ResearchRun.store_id == store_id)
        .where(ResearchRun.run_type.notin_([ResearchRunType.discovery, ResearchRunType.verification]))
        .order_by(ResearchRun.created_at.desc())  # type: ignore[arg-type]
    ).first()


def _latest_published_understanding_run(session: Session, store_id: uuid.UUID) -> ResearchRun | None:
    """Latest run whose crawl is complete.

    A newly queued monitoring run must not replace a valid store report with
    a loading screen.  The active run remains visible through ``latest_run``;
    this query independently selects the last publishable understanding.
    """
    return session.exec(
        select(ResearchRun)
        .join(AgentRun, AgentRun.research_run_id == ResearchRun.id)
        .where(ResearchRun.store_id == store_id)
        .where(AgentRun.agent_type == "crawl_agent_run")
        .where(AgentRun.status == RunStatus.completed)
        .order_by(AgentRun.completed_at.desc())  # type: ignore[arg-type]
    ).first()


def _latest_completed_pipeline_run(session: Session, store_id: uuid.UUID) -> ResearchRun | None:
    return session.exec(
        select(ResearchRun)
        .where(ResearchRun.store_id == store_id)
        .where(ResearchRun.run_type.notin_([ResearchRunType.discovery, ResearchRunType.verification]))
        .where(ResearchRun.status == RunStatus.completed)
        .order_by(ResearchRun.completed_at.desc())  # type: ignore[arg-type]
    ).first()


@router.get("/{store_id}/market-explorations/estimate", response_model=MarketExplorationEstimate)
def estimate_market_exploration(store_id: uuid.UUID, session: Session = Depends(get_session)) -> MarketExplorationEstimate:
    if session.get(Store, store_id) is None:
        raise HTTPException(status_code=404, detail="store not found")
    settings = get_settings()
    provider_name = "serpapi" if settings.evaluation_mode.value == "live" else settings.evaluation_mode.value
    max_queries = 3
    return MarketExplorationEstimate(
        max_queries=max_queries,
        estimated_serp_cost_usd=estimate_search_cost_usd(provider_name) * max_queries,
        includes=["نتائج Google للموضوع", "صفحات وجهات متصدرة", "ترتيب المتجر", "الجهات المتكررة"],
    )


@router.post("/{store_id}/market-explorations", response_model=OnDemandJobResponse, status_code=status.HTTP_202_ACCEPTED)
def run_market_exploration(
    store_id: uuid.UUID,
    payload: MarketExplorationRequest,
    session: Session = Depends(get_session),
) -> OnDemandJobResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    run = ResearchRun(store_id=store.id, run_type=ResearchRunType.discovery, status=RunStatus.pending)
    session.add(run)
    session.commit()
    session.refresh(run)
    agent = AgentRun(research_run_id=run.id, agent_type="on_demand_market_exploration", status=RunStatus.pending, findings={"request": payload.model_dump(), "topic": payload.topic})
    session.add(agent)
    session.commit()
    session.refresh(agent)

    execute_market_exploration_task.delay(str(store.id), str(run.id))
    return OnDemandJobResponse(research_run_id=str(run.id), kind="market_exploration", status="pending")


@router.post("/{store_id}/winning-page-analyses", response_model=OnDemandJobResponse, status_code=status.HTTP_202_ACCEPTED)
def analyze_winning_page(
    store_id: uuid.UUID,
    payload: WinningPageAnalysisRequest,
    session: Session = Depends(get_session),
) -> OnDemandJobResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")
    try:
        market_run_id = uuid.UUID(payload.market_research_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid market_research_run_id") from exc
    market_run = session.get(ResearchRun, market_run_id)
    if market_run is None or market_run.store_id != store.id:
        raise HTTPException(status_code=404, detail="market exploration not found")
    market_agent = session.exec(
        select(AgentRun)
        .where(AgentRun.research_run_id == market_run.id)
        .where(AgentRun.agent_type == "on_demand_market_exploration")
    ).first()
    market_results = (market_agent.findings or {}).get("results", []) if market_agent else []
    competitor_url = str(payload.competitor_url)
    canonical = lambda value: unquote(value).rstrip("/")  # noqa: E731 — local comparison helper only
    allowed = any(item.get("query") == payload.query and canonical(item.get("url", "")) == canonical(competitor_url) for item in market_results)
    if not allowed:
        raise HTTPException(status_code=409, detail="selected page was not observed in this market exploration")
    if payload.target_url:
        target_host = (urlparse(str(payload.target_url)).hostname or "").removeprefix("www.").casefold()
        if target_host != store_domain(store) and not target_host.endswith(f".{store_domain(store)}"):
            raise HTTPException(status_code=409, detail="target_url must belong to the analyzed store")

    run = ResearchRun(store_id=store.id, run_type=ResearchRunType.discovery, status=RunStatus.pending)
    session.add(run); session.commit(); session.refresh(run)
    request = {"market_research_run_id": str(market_run.id), "query": payload.query, "competitor_url": competitor_url, "target_url": str(payload.target_url) if payload.target_url else None}
    agent = AgentRun(research_run_id=run.id, agent_type="on_demand_winning_page_analysis", status=RunStatus.pending, findings={"request": request, "query": payload.query})
    session.add(agent); session.commit(); session.refresh(agent)
    execute_winning_page_analysis_task.delay(str(store.id), str(run.id))
    return OnDemandJobResponse(research_run_id=str(run.id), kind="winning_page_analysis", status="pending")


@router.post(
    "/{store_id}/winning-page-analyses/{analysis_run_id}/convert",
    response_model=ConvertWinningPageAnalysisResponse,
)
def convert_winning_page_analysis(
    store_id: uuid.UUID,
    analysis_run_id: uuid.UUID,
    session: Session = Depends(get_session),
) -> ConvertWinningPageAnalysisResponse:
    store = session.get(Store, store_id)
    run = session.get(ResearchRun, analysis_run_id)
    if store is None or run is None or run.store_id != store_id:
        raise HTTPException(status_code=404, detail="winning page analysis not found")
    agent = session.exec(
        select(AgentRun)
        .where(AgentRun.research_run_id == run.id)
        .where(AgentRun.agent_type == "on_demand_winning_page_analysis")
    ).first()
    findings = agent.findings if agent and agent.status == RunStatus.completed else None
    if not findings:
        raise HTTPException(status_code=409, detail="winning page analysis is not completed")

    execution_id = uuid.UUID(findings["ai_execution_id"])
    evidence = session.exec(
        select(Evidence)
        .where(Evidence.source_type == EvidenceSourceType.ai_execution)
        .where(Evidence.source_id == execution_id)
    ).first()
    if evidence is None:
        evidence = Evidence(
            store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.ai_execution,
            source_id=execution_id, confidence=0.75,
            summary=f"مقارنة صفحة متصدرة للاستعلام '{findings['query']}': {findings['analysis']['summary']}",
        )
        session.add(evidence); session.commit(); session.refresh(evidence)

    matching_intent = session.exec(
        select(Intent)
        .where(Intent.store_id == store.id)
        .where(Intent.topic == findings["query"])
        .where(Intent.stable_intent_id.is_not(None))
        .order_by(Intent.created_at.desc())  # type: ignore[attr-defined]
    ).first()
    target_url = findings.get("target_url")
    analysis = findings["analysis"]
    draft = OpportunityDraft(
        opportunity_type="page_rebuild_gap",
        title=f"إعادة بناء تغطية '{findings['query']}'",
        description=f"{analysis['summary']} الفجوات المرصودة: {'، '.join(analysis.get('gaps') or [])}",
        fingerprint_target=f"{findings['query']}|{findings['competitor_url']}|{target_url or 'missing-page'}",
        affected_intents=[str(matching_intent.stable_intent_id)] if matching_intent else [],
        affected_queries=[findings["query"]],
        affected_pages=[target_url] if target_url else [],
        evidence_ids=[str(evidence.id)],
        competitor_gap=0.8,
        estimated_impact=0.7,
        confidence=0.75,
        effort_estimate="medium",
        commercial_relevance=0.8 if matching_intent and matching_intent.commercial_stage and matching_intent.commercial_stage.value == "purchase" else 0.6,
    )
    opportunity = persist_on_demand_opportunity(session, store.id, run.id, draft, analysis)
    recommendations = run_recommendation_engine(session, store.id, run.id, [opportunity], max_recommendations=1)
    if not recommendations:
        raise HTTPException(status_code=409, detail="analysis did not pass recommendation evidence checks")
    recommendation = recommendations[0]
    return ConvertWinningPageAnalysisResponse(
        opportunity_id=str(opportunity.id), recommendation_id=str(recommendation.id), recommendation_title=recommendation.title,
    )


@router.get("/{store_id}/on-demand-analyses", response_model=OnDemandAnalysisHistoryResponse)
def list_on_demand_analyses(
    store_id: uuid.UUID,
    session: Session = Depends(get_session),
) -> OnDemandAnalysisHistoryResponse:
    if session.get(Store, store_id) is None:
        raise HTTPException(status_code=404, detail="store not found")
    runs = session.exec(
        select(ResearchRun)
        .where(ResearchRun.store_id == store_id)
        .where(ResearchRun.run_type == ResearchRunType.discovery)
        .order_by(ResearchRun.created_at.desc())  # type: ignore[attr-defined]
        .limit(50)
    ).all()
    items: list[OnDemandAnalysisHistoryItem] = []
    for run in runs:
        agent = session.exec(
            select(AgentRun)
            .where(AgentRun.research_run_id == run.id)
            .where(AgentRun.agent_type.in_(["on_demand_market_exploration", "on_demand_winning_page_analysis"]))  # type: ignore[attr-defined]
        ).first()
        if agent is None:
            continue
        findings = agent.findings or {}
        serp_cost = sum((row.cost_usd or 0.0) for row in session.exec(select(SerpExecution).where(SerpExecution.research_run_id == run.id)).all())
        ai_cost = sum((row.cost_usd or 0.0) for row in session.exec(select(AIExecution).where(AIExecution.research_run_id == run.id)).all())
        recommendation = None
        if agent.agent_type == "on_demand_winning_page_analysis":
            opportunity = session.exec(
                select(Opportunity)
                .where(Opportunity.research_run_id == run.id)
                .where(Opportunity.opportunity_type == "page_rebuild_gap")
            ).first()
            if opportunity:
                recommendation = session.exec(select(Recommendation).where(Recommendation.opportunity_id == opportunity.id)).first()
        items.append(OnDemandAnalysisHistoryItem(
            research_run_id=str(run.id),
            kind="market_exploration" if agent.agent_type == "on_demand_market_exploration" else "winning_page_analysis",
            status=run.status.value,
            topic=findings.get("topic") or findings.get("query") or "تحليل عند الطلب",
            summary=(findings.get("analysis") or {}).get("summary"),
            created_at=_iso_utc(run.created_at) or "",
            completed_at=_iso_utc(run.completed_at),
            serp_cost_usd=serp_cost,
            ai_cost_usd=ai_cost,
            recommendation_id=str(recommendation.id) if recommendation else None,
            recommendation_title=recommendation.title if recommendation else None,
        ))
    return OnDemandAnalysisHistoryResponse(analyses=items)


_JOB_KINDS = {
    "on_demand_market_exploration": "market_exploration",
    "on_demand_winning_page_analysis": "winning_page_analysis",
    "on_demand_implementation_generation": "implementation_generation",
}


@router.get("/{store_id}/on-demand-analyses/{research_run_id}/status", response_model=OnDemandJobStatus)
def get_on_demand_job_status(
    store_id: uuid.UUID, research_run_id: uuid.UUID, session: Session = Depends(get_session),
) -> OnDemandJobStatus:
    run = session.get(ResearchRun, research_run_id)
    if run is None or run.store_id != store_id:
        raise HTTPException(status_code=404, detail="on-demand analysis not found")
    agent = session.exec(select(AgentRun).where(AgentRun.research_run_id == run.id)).first()
    if agent is None or agent.agent_type not in _JOB_KINDS:
        raise HTTPException(status_code=404, detail="on-demand analysis not found")
    findings = agent.findings or {}
    return OnDemandJobStatus(
        research_run_id=str(run.id), kind=_JOB_KINDS[agent.agent_type], status=run.status.value,
        error=run.error or agent.error, result=findings.get("result"),
    )


@router.post("/{store_id}/on-demand-analyses/{research_run_id}/retry", response_model=OnDemandJobResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_on_demand_job(
    store_id: uuid.UUID, research_run_id: uuid.UUID, session: Session = Depends(get_session),
) -> OnDemandJobResponse:
    run = session.get(ResearchRun, research_run_id)
    if run is None or run.store_id != store_id or run.status not in {RunStatus.failed, RunStatus.cancelled}:
        raise HTTPException(status_code=409, detail="only failed or cancelled jobs can be retried")
    agent = session.exec(select(AgentRun).where(AgentRun.research_run_id == run.id)).first()
    if agent is None or agent.agent_type not in _JOB_KINDS:
        raise HTTPException(status_code=404, detail="on-demand analysis not found")
    run.status = RunStatus.pending; run.error = None; run.started_at = None; run.completed_at = None
    agent.status = RunStatus.pending; agent.error = None; agent.started_at = None; agent.completed_at = None
    session.add(run); session.add(agent); session.commit()
    if agent.agent_type == "on_demand_market_exploration":
        execute_market_exploration_task.delay(str(store_id), str(run.id))
    elif agent.agent_type == "on_demand_winning_page_analysis":
        execute_winning_page_analysis_task.delay(str(store_id), str(run.id))
    else:
        from app.workers.tasks import execute_implementation_generation_task
        execute_implementation_generation_task.delay(str(store_id), str(run.id))
    return OnDemandJobResponse(research_run_id=str(run.id), kind=_JOB_KINDS[agent.agent_type], status="pending")


@router.get("/{store_id}/market-explorations/{research_run_id}", response_model=MarketExplorationResponse)
def get_market_exploration(
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    session: Session = Depends(get_session),
) -> MarketExplorationResponse:
    run = session.get(ResearchRun, research_run_id)
    if run is None or run.store_id != store_id:
        raise HTTPException(status_code=404, detail="market exploration not found")
    agent = session.exec(select(AgentRun).where(AgentRun.research_run_id == run.id).where(AgentRun.agent_type == "on_demand_market_exploration")).first()
    if agent is None or not agent.findings:
        raise HTTPException(status_code=404, detail="market exploration not found")
    data = agent.findings
    return MarketExplorationResponse(
        research_run_id=str(run.id), status=run.status.value, topic=data["topic"], queries=data.get("queries", []),
        results=[MarketExplorationResultItem.model_validate(item) for item in data.get("results", [])],
        client_ranks=data.get("client_ranks", {}), recurring_domains=data.get("recurring_domains", []),
        actual_serp_cost_usd=data.get("actual_serp_cost_usd", 0.0), warnings=agent.warnings,
    )


@router.get("/{store_id}/winning-page-analyses/{research_run_id}", response_model=WinningPageAnalysisResponse)
def get_winning_page_analysis(
    store_id: uuid.UUID,
    research_run_id: uuid.UUID,
    session: Session = Depends(get_session),
) -> WinningPageAnalysisResponse:
    run = session.get(ResearchRun, research_run_id)
    if run is None or run.store_id != store_id:
        raise HTTPException(status_code=404, detail="winning page analysis not found")
    agent = session.exec(select(AgentRun).where(AgentRun.research_run_id == run.id).where(AgentRun.agent_type == "on_demand_winning_page_analysis")).first()
    if agent is None or not agent.findings:
        raise HTTPException(status_code=404, detail="winning page analysis not found")
    data = agent.findings
    execution = session.get(AIExecution, uuid.UUID(data["ai_execution_id"]))
    return WinningPageAnalysisResponse(
        research_run_id=str(run.id), status=run.status.value, query=data["query"], competitor_url=data["competitor_url"],
        target_url=data.get("target_url"), competitor_facts=data.get("competitor_facts", {}), target_facts=data.get("target_facts"),
        output=WinningPageAnalysisOutput.model_validate(data["analysis"]), ai_execution_id=data["ai_execution_id"],
        ai_cost_usd=execution.cost_usd if execution else None,
    )


def _iso_utc(value: datetime | None) -> str | None:
    """API timestamps are UTC even when a test/DB driver returns them naive."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _get_or_create_default_organization(session: Session) -> Organization:
    existing = session.exec(select(Organization).where(Organization.slug == "default")).first()
    if existing:
        return existing
    org = Organization(name="Default", slug="default")
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


@router.post("", response_model=CreateStoreResponse)
def create_store(payload: CreateStoreRequest, session: Session = Depends(get_session)) -> CreateStoreResponse:
    organization = (
        session.get(Organization, payload.organization_id)
        if payload.organization_id
        else _get_or_create_default_organization(session)
    )
    if organization is None:
        raise HTTPException(status_code=404, detail="organization not found")

    store = Store(
        organization_id=organization.id,
        url=payload.url,
        country=payload.country,
        language=payload.language,
    )
    session.add(store)
    session.commit()
    session.refresh(store)

    run = ResearchOrchestrator.create_pending_run(session, store)
    execute_research_run_task.delay(str(store.id), str(run.id))

    return CreateStoreResponse(store_id=store.id, research_run_id=run.id, status=run.status.value)


@router.post("/{store_id}/research-runs", response_model=CreateStoreResponse)
def trigger_research_run(store_id: uuid.UUID, session: Session = Depends(get_session)) -> CreateStoreResponse:
    """Manual re-run trigger (Group F — 'manual' monitoring_cadence needs
    this, and it's also what a future 'Run Now' button in the Research
    page calls). Scheduled runs (Part F7) go through the same
    ResearchOrchestrator.create_pending_run + execute_research_run_task
    path via app/workers/scheduling.py — this is just the on-demand
    entry point for an existing store."""
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    latest_run = _latest_pipeline_run(session, store_id)
    if latest_run is not None and latest_run.status in (RunStatus.pending, RunStatus.running):
        raise HTTPException(status_code=409, detail="a research run is already in progress for this store")

    run_type = ResearchRunType.baseline if latest_run is None else ResearchRunType.monitoring
    run = ResearchOrchestrator.create_pending_run(session, store, run_type=run_type)
    execute_research_run_task.delay(str(store.id), str(run.id))

    return CreateStoreResponse(store_id=store.id, research_run_id=run.id, status=run.status.value)


@router.post("/{store_id}/research-runs/{run_id}/cancel", response_model=CancelResearchRunResponse)
def cancel_research_run(
    store_id: uuid.UUID, run_id: uuid.UUID, session: Session = Depends(get_session)
) -> CancelResearchRunResponse:
    """Part H8 — stops further research task dispatch as soon as the
    iterative loop next polls (between batches, not mid-batch — in-flight
    work is allowed to finish rather than being torn down mid-write). The
    fixed pipeline steps and downstream opportunity/recommendation/
    monitoring steps still run against whatever research did complete; the
    run's final status becomes RunStatus.cancelled instead of
    RunStatus.completed so this is never mistaken for a normal finish."""
    run = session.get(ResearchRun, run_id)
    if run is None or run.store_id != store_id:
        raise HTTPException(status_code=404, detail="research run not found")

    accepted = request_run_cancellation(session, run_id)
    return CancelResearchRunResponse(research_run_id=run_id, cancellation_requested=accepted)


@router.get("/{store_id}", response_model=StoreDetailResponse)
def get_store(store_id: uuid.UUID, session: Session = Depends(get_session)) -> StoreDetailResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    pages_crawled = session.exec(select(func.count()).select_from(Page).where(Page.store_id == store_id)).one()
    products_found = session.exec(select(func.count()).select_from(Product).where(Product.store_id == store_id)).one()
    categories_found = session.exec(
        select(func.count()).select_from(Category).where(Category.store_id == store_id)
    ).one()
    competitors_found = session.exec(
        select(func.count()).select_from(Competitor).where(Competitor.store_id == store_id)
    ).one()

    latest_run = _latest_pipeline_run(session, store_id)
    analysis_run = (
        latest_run if latest_run is not None and latest_run.status == RunStatus.completed
        else _latest_completed_pipeline_run(session, store_id)
    )

    total_ai_cost_usd = 0.0
    total_serp_cost_usd = 0.0
    intents_found = 0
    visibility_summary = None
    ai_visibility_summary = None
    research_summary = None
    latest_run_summary = None
    classification = None
    if analysis_run is not None:
        cost_row = session.exec(
            select(func.coalesce(func.sum(AIExecution.cost_usd), 0.0)).where(
                AIExecution.research_run_id == analysis_run.id
            )
        ).one()
        total_ai_cost_usd = float(cost_row or 0.0)

        serp_cost_row = session.exec(
            select(func.coalesce(func.sum(SerpExecution.cost_usd), 0.0)).where(
                SerpExecution.research_run_id == analysis_run.id
            )
        ).one()
        total_serp_cost_usd = float(serp_cost_row or 0.0)

        intents_found = session.exec(
            select(func.count()).select_from(Intent).where(Intent.research_run_id == analysis_run.id)
        ).one()

        metrics = compute_visibility_metrics(session, analysis_run.id)
        if metrics.total_intents_measured > 0:
            visibility_summary = VisibilitySummary(
                total_intents_measured=metrics.total_intents_measured,
                ranking_coverage=metrics.ranking_coverage,
                top3_rate=metrics.top3_rate,
                top10_rate=metrics.top10_rate,
                avg_client_rank=metrics.avg_client_rank,
            )

        ai_metrics = compute_ai_visibility_metrics(session, analysis_run.id)
        if ai_metrics.total_observations > 0:
            ai_visibility_summary = AIVisibilitySummary(
                total_observations=ai_metrics.total_observations,
                mention_rate=ai_metrics.mention_rate,
                intent_coverage=ai_metrics.intent_coverage,
                citation_rate=ai_metrics.citation_rate,
                stability=ai_metrics.stability,
            )

        agent_runs = session.exec(select(AgentRun).where(AgentRun.research_run_id == analysis_run.id)).all()

        classification_run = next((ar for ar in agent_runs if ar.agent_type == "ai_classification_agent_run"), None)
        if classification_run is not None and classification_run.findings:
            classification = classification_run.findings

        iterative_run = next((ar for ar in agent_runs if ar.agent_type == "iterative_research_agent_run"), None)
        if iterative_run is not None and iterative_run.findings:
            research_summary = ResearchSummary(**iterative_run.findings)

    if latest_run is not None:
        progress_agent_runs = session.exec(select(AgentRun).where(AgentRun.research_run_id == latest_run.id)).all()
        latest_run_summary = ResearchRunSummary(
            id=latest_run.id,
            run_type=latest_run.run_type.value,
            status=latest_run.status.value,
            created_at=_iso_utc(latest_run.created_at),
            started_at=_iso_utc(latest_run.started_at),
            completed_at=_iso_utc(latest_run.completed_at),
            error=latest_run.error,
            agent_runs=[
                AgentRunSummary(
                    agent_type=ar.agent_type,
                    status=ar.status.value,
                    started_at=_iso_utc(ar.started_at),
                    completed_at=_iso_utc(ar.completed_at),
                    findings=ar.findings,
                    error=ar.error,
                )
                for ar in progress_agent_runs
            ],
        )

    return StoreDetailResponse(
        id=store.id,
        url=store.url,
        status=store.status.value,
        pages_crawled=pages_crawled,
        products_found=products_found,
        categories_found=categories_found,
        total_ai_cost_usd=total_ai_cost_usd,
        intents_found=intents_found,
        total_serp_cost_usd=total_serp_cost_usd,
        competitors_found=competitors_found,
        visibility_summary=visibility_summary,
        ai_visibility_summary=ai_visibility_summary,
        research_summary=research_summary,
        store_profile=build_store_profile(session, store, classification),
        latest_run=latest_run_summary,
        component_snapshots={
            component: ComponentSnapshotItem(
                research_run_id=snapshot.research_run_id,
                status=snapshot.status,
                progress_completed=snapshot.progress_completed,
                progress_total=snapshot.progress_total,
                payload=snapshot.payload,
                started_at=_iso_utc(snapshot.started_at),
                completed_at=_iso_utc(snapshot.completed_at),
                error=snapshot.error,
            )
            for component, snapshot in latest_component_snapshots(session, store_id).items()
        },
    )


@router.get("/{store_id}/understanding", response_model=StoreUnderstandingResponse)
def get_store_understanding(store_id: uuid.UUID, session: Session = Depends(get_session)) -> StoreUnderstandingResponse:
    """Progressive "فهمنا متجرك" summary — deliberately independent of the
    full research pipeline. understanding_stage only depends on the crawl
    and classification steps (the first 2 of 9), so the frontend can show
    this the moment those finish instead of waiting for SERP/AI-visibility/
    competitors/opportunities/recommendations."""
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    pages_crawled = session.exec(select(func.count()).select_from(Page).where(Page.store_id == store_id)).one()
    products_found = session.exec(select(func.count()).select_from(Product).where(Product.store_id == store_id)).one()
    categories_found = session.exec(
        select(func.count()).select_from(Category).where(Category.store_id == store_id)
    ).one()
    brands_found = session.exec(select(func.count()).select_from(Brand).where(Brand.store_id == store_id)).one()

    # A previously-published understanding (a completed crawl from an
    # earlier run) always wins first, so a newly-queued monitoring run
    # never regresses the store's page back to a loading screen. Only when
    # nothing has ever been published (the common brand-new-store case)
    # do we fall back to the currently in-flight run — this is what lets
    # identity_run's progress be visible *before* the crawl finishes,
    # which is the entire point of decoupling identity from the crawl.
    latest_run = _latest_published_understanding_run(session, store_id)
    if latest_run is None:
        latest_run = _latest_pipeline_run(session, store_id)

    understanding_stage = "pending"
    business_type = None
    country: str | None = None
    city: str | None = None
    primary_categories: list[str] = []
    target_audience: list[str] = []
    classification_confidence = None
    classification_skipped = False
    last_analyzed_at = None
    crawl_run = None
    classification_run = None
    identity_run = None
    identity_confidence = None
    identity_brand_name = None
    identity_skipped = False

    if latest_run is not None:
        agent_runs = session.exec(select(AgentRun).where(AgentRun.research_run_id == latest_run.id)).all()
        crawl_run = next((ar for ar in agent_runs if ar.agent_type == "crawl_agent_run"), None)
        classification_run = next((ar for ar in agent_runs if ar.agent_type == "ai_classification_agent_run"), None)
        identity_run = next((ar for ar in agent_runs if ar.agent_type == "store_identity_agent_run"), None)

        if crawl_run is not None and crawl_run.status == RunStatus.completed:
            last_analyzed_at = _iso_utc(crawl_run.completed_at)

        if classification_run is not None and classification_run.findings:
            findings = classification_run.findings
            classification_skipped = bool(findings.get("skipped"))
            raw_business_type = findings.get("business_type")
            business_type = unescape(raw_business_type) if isinstance(raw_business_type, str) else None
            primary_categories = [unescape(str(v)) for v in findings.get("primary_categories", []) if v]
            target_audience = [unescape(str(v)) for v in findings.get("target_audience", []) if v]
            confidence = findings.get("confidence")
            classification_confidence = float(confidence) if isinstance(confidence, (int, float)) else None

        if identity_run is not None and identity_run.findings:
            identity_findings = identity_run.findings
            identity_skipped = bool(identity_findings.get("skipped"))
            if not identity_skipped:
                raw_brand_name = identity_findings.get("brand_name")
                identity_brand_name = unescape(raw_brand_name) if isinstance(raw_brand_name, str) else None
                raw_identity_confidence = identity_findings.get("confidence")
                identity_confidence = (
                    float(raw_identity_confidence) if isinstance(raw_identity_confidence, (int, float)) else None
                )
                # A resolved identity is at least as good a business_type/
                # category signal as crawl-derived classification — prefer
                # it when classification didn't produce one (never
                # overwrite a real classification result, only fill gaps).
                if not business_type:
                    raw_identity_business_type = identity_findings.get("business_type")
                    business_type = (
                        unescape(raw_identity_business_type) if isinstance(raw_identity_business_type, str) else None
                    )
                if not primary_categories:
                    primary_categories = [unescape(str(v)) for v in identity_findings.get("categories", []) if v]
                if not target_audience:
                    target_audience = [unescape(str(v)) for v in identity_findings.get("target_audiences", []) if v]
                raw_country = identity_findings.get("country")
                country = unescape(raw_country) if isinstance(raw_country, str) and raw_country else None
                raw_city = identity_findings.get("city")
                city = unescape(raw_city) if isinstance(raw_city, str) and raw_city else None

        understanding_stage = resolve_understanding_stage(
            crawl_run=crawl_run,
            classification_run=classification_run,
            classification_confidence=classification_confidence,
            classification_skipped=classification_skipped,
            identity_run=identity_run,
            identity_confidence=identity_confidence,
            identity_brand_name=identity_brand_name,
            identity_skipped=identity_skipped,
            catalog_status=store.catalog_status,
        )

    if not country and store.country:
        country = store.country

    category_rows = session.exec(
        select(Category.id, Category.name, Category.url, func.count(Product.id))
        .select_from(Category)
        .outerjoin(Product, Product.category_id == Category.id)  # type: ignore[arg-type]
        .where(Category.store_id == store_id)
        .group_by(Category.id, Category.name, Category.url)
        .order_by(func.count(Product.id).desc())
        .limit(8)
    ).all()
    top_categories = [TopCategoryItem(id=row[0], name=unescape(row[1]), product_count=row[3]) for row in category_rows]

    product_rows = session.exec(
        select(Product, Category.name)
        .select_from(Product)
        .outerjoin(Category, Product.category_id == Category.id)  # type: ignore[arg-type]
        .where(Product.store_id == store_id)
        .order_by(Product.created_at.desc())  # type: ignore[arg-type]
        .limit(8)
    ).all()
    product_samples = [
        ProductSampleItem(
            id=product.id, name=unescape(product.name), url=product.url,
            category_name=unescape(category_name) if category_name else None,
            price=product.price, currency=product.currency, image_url=product.image_url,
        )
        for product, category_name in product_rows
    ]

    # Some storefronts expose valid Product JSON-LD on route shapes that are
    # intentionally not promoted to canonical Product rows. Surface those
    # observed facts as non-clickable previews so the understanding page does
    # not discard real names/images or inflate the canonical product count.
    profile = build_store_profile(session, store, classification_run.findings if classification_run else None)
    if not product_samples:
        if profile is not None:
            product_samples = [
                ProductSampleItem(
                    id=uuid.uuid5(uuid.NAMESPACE_URL, item.url), name=unescape(item.name),
                    url=item.url, image_url=item.image_url, detail_available=False,
                )
                for item in profile.products[:8]
            ]

    category_previews = build_category_previews(
        primary_categories,
        [(str(row[1]), row[2], int(row[3])) for row in category_rows],
        profile.products if profile else [],
        classification_confidence,
    )
    observations = session.exec(
        select(PageObservation).where(PageObservation.store_id == store_id).order_by(PageObservation.observed_at.desc())  # type: ignore[arg-type]
    ).all()
    page_links: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for observation in observations:
        if observation.source_url in seen_urls:
            continue
        seen_urls.add(observation.source_url)
        extraction = observation.normalized_extraction or {}
        title = extraction.get("title") or extraction.get("h1") or ""
        page_links.append((str(title), observation.source_url))
        for link in extraction.get("internal_links") or []:
            if isinstance(link, str):
                page_links.append((link, link))
    business_info = build_business_info(page_links)

    sold_brands = []
    if profile:
        store_name = (profile.name or "").strip().casefold()
        sold_brands = [name for name in profile.brands if name.strip().casefold() != store_name]

    brand_row = session.exec(select(Brand).where(Brand.store_id == store_id)).first()
    brand = None
    if brand_row is not None:
        brand = BrandItem(
            name=unescape(brand_row.name),
            aliases=[unescape(a) for a in brand_row.aliases],
            is_guessed=brand_row.name == _guess_brand_name_from_domain(store.url),
        )

    display_name = brand.name if brand is not None and not brand.is_guessed else None
    if not display_name and identity_brand_name:
        # A crawl-derived brand never showed up (blocked/empty site), but
        # web search resolved one — this is the actual point of Phase 1:
        # a real, sourced name instead of "لم نتأكد من الاسم".
        display_name = identity_brand_name
    if not display_name:
        # Both prior tiers exhausted (no real crawl-extracted Brand.name,
        # web search skipped/failed) — extended fallback chain over
        # already-crawled data, never blocking: structured data -> og:
        # site_name -> page title -> logo alt -> domain-derived name (the
        # last tier never fails). Confirmed live on modernsupply.com.sa,
        # where web_search failed but crawl+classification alone already
        # had everything needed.
        home_page = session.exec(
            select(Page).where(Page.store_id == store_id, Page.page_type == "home")
        ).first()
        home_extraction: dict = {}
        if home_page is not None:
            home_observation = next((o for o in observations if o.source_url == home_page.url), None)
            if home_observation is not None:
                home_extraction = home_observation.normalized_extraction or {}
        display_name, _display_name_source = resolve_best_available_name(
            home_extraction=home_extraction, base_url=store.url
        )

    identity_competitors = session.exec(
        select(Competitor).where(
            Competitor.store_id == store_id, Competitor.competitor_type == CompetitorType.identity_web_search
        )
    ).all()
    suggested_competitors = [
        SuggestedCompetitorItem(
            id=c.id, domain=c.domain, name=c.name, confirmation_status=c.confirmation_status,
            classification_confidence=c.classification_confidence, discovery_reason=c.discovery_reason,
        )
        for c in identity_competitors
        if c.confirmation_status != "user_rejected"
    ]

    return StoreUnderstandingResponse(
        understanding_stage=understanding_stage,
        display_name=display_name,
        description=profile.description if profile else None,
        url=store.url,
        business_type=business_type,
        country=country,
        city=city,
        primary_categories=primary_categories,
        target_audience=target_audience,
        classification_confidence=classification_confidence,
        classification_skipped=classification_skipped,
        identity_source=store.identity_source,
        identity_confidence=store.identity_confidence,
        catalog_status=store.catalog_status,
        catalog_products_found=store.catalog_products_found,
        competitor_discovery_status=store.competitor_discovery_status,
        suggested_competitors=suggested_competitors,
        pages_crawled=pages_crawled,
        products_found=products_found,
        categories_found=categories_found,
        brands_found=brands_found,
        top_categories=top_categories,
        product_samples=product_samples,
        category_previews=category_previews,
        product_count_status="confirmed" if products_found > 0 else "unavailable",
        estimated_products_count=None,
        sold_brands=sold_brands,
        business_info=business_info,
        audience_basis="فرضية مبنية على نوع النشاط والتصنيفات المرصودة؛ لا تُستخدم كتوصية قبل تأكيدك." if target_audience else None,
        brand=brand,
        last_analyzed_at=last_analyzed_at,
    )


@router.post("/{store_id}/brand-name", response_model=BrandNameConfirmResponse)
def confirm_store_brand_name(
    store_id: uuid.UUID, payload: BrandNameConfirmRequest, session: Session = Depends(get_session)
) -> BrandNameConfirmResponse:
    """User-edited/confirmed name from the /signup identity screen —
    persisted so it survives past this browser session, and so future
    visibility-analysis runs ground their brand-mention detection on it.
    The previously-resolved name (whatever tier of the fallback chain
    produced it — real crawl data, web search, or a domain guess) and the
    store's own domain both become aliases rather than being discarded, so
    an AI answer that still uses the old name/domain-derived guess is
    still correctly recognized as mentioning this brand."""
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    new_name = payload.name.strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="name is required")

    domain = registered_hostname(store.url)
    brand = session.exec(select(Brand).where(Brand.store_id == store_id)).first()

    aliases: set[str] = {domain}
    if brand is not None:
        aliases.update(brand.aliases or [])
        if brand.name and brand.name.strip() and brand.name.strip() != new_name:
            aliases.add(brand.name.strip())
        brand.name = new_name
        brand.aliases = sorted(a for a in aliases if a and a != new_name)
        session.add(brand)
    else:
        brand = Brand(store_id=store_id, name=new_name, aliases=sorted(a for a in aliases if a and a != new_name))
        session.add(brand)

    session.commit()
    session.refresh(brand)
    return BrandNameConfirmResponse(name=brand.name, aliases=brand.aliases)


@router.post("/{store_id}/understanding/feedback", response_model=StoreFeedbackResponse)
def submit_store_understanding_feedback(
    store_id: uuid.UUID, payload: StoreFeedbackRequest, session: Session = Depends(get_session)
) -> StoreFeedbackResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")
    if payload.feedback_type not in ("confirmed", "incorrect"):
        raise HTTPException(status_code=422, detail="feedback_type must be 'confirmed' or 'incorrect'")

    latest_run = _latest_pipeline_run(session, store_id)
    if latest_run is None:
        raise HTTPException(status_code=409, detail="no research run exists for this store yet")

    feedback = StoreFeedback(
        store_id=store_id,
        research_run_id=latest_run.id,
        feedback_type=payload.feedback_type,
        issues=payload.issues,
        note=payload.note,
    )
    session.add(feedback)
    session.commit()
    session.refresh(feedback)

    return StoreFeedbackResponse(
        id=feedback.id,
        feedback_type=feedback.feedback_type,
        issues=feedback.issues,
        note=feedback.note,
        created_at=_iso_utc(feedback.created_at) or "",
    )


def _latest_product_observation(session: Session, product: Product) -> PageObservation | None:
    return session.exec(
        select(PageObservation)
        .where(PageObservation.store_id == product.store_id)
        .where(PageObservation.source_url == product.url)
        .order_by(PageObservation.observed_at.desc())  # type: ignore[arg-type]
    ).first()


def _latest_page_observation(session: Session, page: Page) -> PageObservation | None:
    return session.exec(
        select(PageObservation)
        .where(PageObservation.store_id == page.store_id)
        .where(PageObservation.page_id == page.id)
        .order_by(PageObservation.observed_at.desc())  # type: ignore[arg-type]
    ).first()


def _page_workspace_item(session: Session, page: Page) -> PageWorkspaceItem:
    observation = _latest_page_observation(session, page)
    extraction = observation.normalized_extraction if observation else {}
    checks = general_page_checks(extraction, page_type=page.page_type or "other")
    images = extraction.get("images") or []
    image_url = next((item.get("url") for item in images if isinstance(item, dict) and item.get("url")), None)
    return PageWorkspaceItem(
        id=page.id, url=page.url, page_type=page.page_type or "other",
        title=extraction.get("title"), h1=extraction.get("h1"), image_url=image_url,
        completion_score=completion_score(checks),
        issues_count=sum(check.status == "missing" for check in checks),
        observed_at=_iso_utc(observation.observed_at) if observation else None,
    )


@router.get("/{store_id}/pages", response_model=PageWorkspaceListResponse)
def list_page_workspaces(store_id: uuid.UUID, session: Session = Depends(get_session)) -> PageWorkspaceListResponse:
    if session.get(Store, store_id) is None:
        raise HTTPException(status_code=404, detail="store not found")
    pages = session.exec(
        select(Page).where(Page.store_id == store_id).order_by(Page.created_at.desc())  # type: ignore[arg-type]
    ).all()
    return PageWorkspaceListResponse(pages=[_page_workspace_item(session, page) for page in pages])


@router.get("/{store_id}/pages/{page_id}", response_model=PageWorkspaceResponse)
def get_page_workspace(store_id: uuid.UUID, page_id: uuid.UUID, session: Session = Depends(get_session)) -> PageWorkspaceResponse:
    page = session.get(Page, page_id)
    if page is None or page.store_id != store_id:
        raise HTTPException(status_code=404, detail="page not found")
    base = _page_workspace_item(session, page)
    observation = _latest_page_observation(session, page)
    extraction = observation.normalized_extraction if observation else {}
    checks = general_page_checks(extraction, page_type=page.page_type or "other")
    linked: list[ProductWorkspaceRecommendationItem] = []
    recommendations = session.exec(
        select(Recommendation).where(Recommendation.store_id == store_id)
        .where(Recommendation.status != RecommendationStatus.needs_validation)
        .order_by(Recommendation.priority_score.desc())  # type: ignore[arg-type]
    ).all()
    for recommendation in recommendations:
        if recommendation.page_id == page.id:
            basis = "page_id"
        elif canonical_store_url(recommendation.target_page) == canonical_store_url(page.url):
            basis = "canonical_url"
        else:
            continue
        linked.append(ProductWorkspaceRecommendationItem(
            id=recommendation.id, title=recommendation.title, status=recommendation.status.value,
            link_basis=basis, implementation=implementation_fields(recommendation.implementation_package),
        ))
    return PageWorkspaceResponse(
        **base.model_dump(), current=extraction,
        checks=[ProductPageCheckItem(**check.__dict__) for check in checks], recommendations=linked,
    )


@router.post("/{store_id}/pages/{page_id}/screenshot", response_model=CapturePageScreenshotResponse)
async def create_page_screenshot(
    store_id: uuid.UUID,
    page_id: uuid.UUID,
    payload: CapturePageScreenshotRequest,
    session: Session = Depends(get_session),
) -> CapturePageScreenshotResponse:
    page = session.get(Page, page_id)
    if page is None or page.store_id != store_id:
        raise HTTPException(status_code=404, detail="page not found")
    try:
        screenshot, width, height, annotations = await capture_page_screenshot(page.url, mobile=payload.mobile)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"could not capture page: {exc}") from exc
    storage = get_storage()
    uri = storage.put_bytes(f"stores/{store_id}/page-screenshots", screenshot, "image/png")
    observation = _latest_page_observation(session, page)
    if observation is not None:
        entities = dict(observation.extracted_entities or {})
        screenshots = dict(entities.get("screenshots") or {})
        screenshots["mobile" if payload.mobile else "desktop"] = uri
        entities["screenshots"] = screenshots
        observation.extracted_entities = entities
        session.add(observation)
        session.commit()
    return CapturePageScreenshotResponse(
        screenshot_url=storage.presigned_url(uri), mobile=payload.mobile,
        width=width, height=height, annotations=annotations,
    )


def _product_category_name(session: Session, product: Product) -> str | None:
    if product.category_id is None:
        return None
    category = session.get(Category, product.category_id)
    return unescape(category.name) if category else None


def _product_link_suggestions(session: Session, product: Product) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    if product.category_id is not None:
        category = session.get(Category, product.category_id)
        if category and category.url:
            suggestions.append({"label": unescape(category.name), "url": category.url, "kind": "category"})
        siblings = session.exec(
            select(Product).where(Product.category_id == product.category_id).where(Product.id != product.id).limit(6)
        ).all()
        suggestions.extend({"label": unescape(item.name), "url": item.url, "kind": "product"} for item in siblings)
    return suggestions


@router.get("/{store_id}/categories", response_model=CategoryWorkspaceListResponse)
def list_category_workspaces(store_id: uuid.UUID, session: Session = Depends(get_session)) -> CategoryWorkspaceListResponse:
    if session.get(Store, store_id) is None:
        raise HTTPException(status_code=404, detail="store not found")
    categories = session.exec(
        select(Category).where(Category.store_id == store_id).order_by(Category.name)  # type: ignore[arg-type]
    ).all()
    products = session.exec(select(Product).where(Product.store_id == store_id)).all()
    products_by_category: dict[uuid.UUID, list[Product]] = {}
    for product in products:
        if product.category_id is not None:
            products_by_category.setdefault(product.category_id, []).append(product)
    items: list[CategoryWorkspaceItem] = []
    for category in categories:
        category_products = products_by_category.get(category.id, [])
        observation = session.exec(
            select(PageObservation)
            .where(PageObservation.store_id == store_id)
            .where(PageObservation.source_url == category.url)
            .order_by(PageObservation.observed_at.desc())  # type: ignore[arg-type]
        ).first() if category.url else None
        representative = next((product.image_url for product in category_products if product.image_url), None)
        if representative is None and observation:
            images = (observation.normalized_extraction or {}).get("images") or []
            representative = next((image.get("url") for image in images if isinstance(image, dict) and image.get("url")), None)
        items.append(CategoryWorkspaceItem(
            id=category.id, page_id=observation.page_id if observation else None,
            name=unescape(category.name), url=category.url,
            product_count=len(category_products), representative_image_url=representative,
            confidence=1.0, observed_at=_iso_utc(observation.observed_at) if observation else None,
        ))
    return CategoryWorkspaceListResponse(categories=items)


@router.get("/{store_id}/products", response_model=ProductWorkspaceListResponse)
def list_product_workspaces(store_id: uuid.UUID, session: Session = Depends(get_session)) -> ProductWorkspaceListResponse:
    if session.get(Store, store_id) is None:
        raise HTTPException(status_code=404, detail="store not found")
    products = session.exec(
        select(Product).where(Product.store_id == store_id).order_by(Product.created_at.desc())  # type: ignore[arg-type]
    ).all()
    # Older crawls may have stored tracking/locale variants of the same
    # canonical product. Keep one visual workspace per real product.
    unique_products: dict[str, Product] = {}
    for product in products:
        key = canonical_store_url(product.url) or product.url
        unique_products.setdefault(key, product)
    items: list[ProductWorkspaceItem] = []
    for product in unique_products.values():
        observation = _latest_product_observation(session, product)
        extraction = observation.normalized_extraction if observation else {}
        checks = product_page_checks(extraction, image_url=product.image_url)
        items.append(ProductWorkspaceItem(
            id=product.id, name=unescape(product.name), url=product.url,
            category_name=_product_category_name(session, product), price=product.price,
            currency=product.currency, availability=product.availability, image_url=product.image_url,
            completion_score=completion_score(checks),
            issues_count=sum(check.status == "missing" for check in checks),
            observed_at=_iso_utc(observation.observed_at) if observation else None,
        ))
    return ProductWorkspaceListResponse(products=items)


@router.get("/{store_id}/products/{product_id}", response_model=ProductWorkspaceResponse)
def get_product_detail(
    store_id: uuid.UUID, product_id: uuid.UUID, session: Session = Depends(get_session)
) -> ProductWorkspaceResponse:
    product = session.get(Product, product_id)
    if product is None or product.store_id != store_id:
        raise HTTPException(status_code=404, detail="product not found")

    observation = _latest_product_observation(session, product)
    extraction = observation.normalized_extraction if observation else {}
    checks = product_page_checks(extraction, image_url=product.image_url)
    image_insights = analyze_product_images(extraction, primary_image_url=product.image_url)
    linked_recommendations = []
    recommendations = session.exec(
        select(Recommendation).where(Recommendation.store_id == store_id)
        .where(Recommendation.status != RecommendationStatus.needs_validation)
        .order_by(Recommendation.priority_score.desc())  # type: ignore[arg-type]
    ).all()
    for recommendation in recommendations:
        if recommendation.product_id == product.id:
            link_basis = "product_id"
        else:
            package_urls = (recommendation.implementation_package or {}).get("urls_affected") or []
            linked_urls = {
                canonical_store_url(url)
                for url in [recommendation.target_page, *package_urls]
                if isinstance(url, str)
            }
            if canonical_store_url(product.url) not in linked_urls:
                continue
            link_basis = "canonical_url"
        linked_recommendations.append(ProductWorkspaceRecommendationItem(
            id=recommendation.id, title=recommendation.title, status=recommendation.status.value,
            link_basis=link_basis,
            implementation=implementation_fields(recommendation.implementation_package),
        ))

    return ProductWorkspaceResponse(
        id=product.id,
        name=unescape(product.name),
        url=product.url,
        category_name=_product_category_name(session, product),
        price=product.price,
        currency=product.currency,
        availability=product.availability,
        image_url=product.image_url,
        observed_at=_iso_utc(observation.observed_at) if observation else None,
        current={
            "title": extraction.get("title"), "meta_description": extraction.get("meta_description"),
            "h1": extraction.get("h1"), "canonical": extraction.get("canonical"),
            "description": extract_product_description(extraction),
            "h2": extraction.get("h2") or [], "images": extraction.get("images") or [],
            "faq": extraction.get("faq_items") or [],
            "link_suggestions": _product_link_suggestions(session, product),
        },
        checks=[ProductPageCheckItem(**check.__dict__) for check in checks],
        image_insights=[ProductImageInsightItem(**insight.__dict__) for insight in image_insights],
        completion_score=completion_score(checks),
        recommendations=linked_recommendations,
    )


@router.post("/{store_id}/products/{product_id}/optimize-image", response_model=OptimizeProductImageResponse)
async def optimize_product_image(
    store_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: OptimizeProductImageRequest,
    session: Session = Depends(get_session),
) -> OptimizeProductImageResponse:
    product = session.get(Product, product_id)
    if product is None or product.store_id != store_id:
        raise HTTPException(status_code=404, detail="product not found")
    observation = _latest_product_observation(session, product)
    extraction = observation.normalized_extraction if observation else {}
    allowed_urls = {insight.url for insight in analyze_product_images(extraction, primary_image_url=product.image_url)}
    if payload.image_url not in allowed_urls:
        raise HTTPException(status_code=422, detail="image URL was not observed on this product page")
    try:
        original, optimized, width, height = await download_and_optimize_image(payload.image_url, quality=payload.quality)
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    storage = get_storage()
    uri = storage.put_bytes(f"stores/{store_id}/optimized-images", optimized, "image/webp")
    saved_percent = round(max(0.0, 1 - len(optimized) / len(original)) * 100, 1)
    return OptimizeProductImageResponse(
        original_bytes=len(original), optimized_bytes=len(optimized), saved_percent=saved_percent,
        width=width, height=height, download_url=storage.presigned_url(uri),
    )


@router.get("/{store_id}/intents", response_model=IntentListResponse)
def list_intents(store_id: uuid.UUID, session: Session = Depends(get_session)) -> IntentListResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    intents = session.exec(
        select(Intent).where(Intent.store_id == store_id).order_by(Intent.created_at.desc())  # type: ignore[arg-type]
    ).all()

    intent_ids = [intent.id for intent in intents]
    keyword_links = session.exec(
        select(IntentKeyword).where(IntentKeyword.intent_id.in_(intent_ids))  # type: ignore[union-attr]
    ).all() if intent_ids else []
    keyword_ids = list({link.keyword_id for link in keyword_links})
    keyword_by_id = {
        keyword.id: keyword
        for keyword in (session.exec(select(Keyword).where(Keyword.id.in_(keyword_ids))).all() if keyword_ids else [])  # type: ignore[union-attr]
    }
    links_by_intent: dict[uuid.UUID, list[IntentKeyword]] = {}
    for link in keyword_links:
        links_by_intent.setdefault(link.intent_id, []).append(link)

    latest_observation_by_intent: dict[uuid.UUID, SerpObservation] = {}
    if intent_ids:
        observations = session.exec(
            select(SerpObservation)
            .where(SerpObservation.intent_id.in_(intent_ids))  # type: ignore[union-attr]
            .order_by(SerpObservation.observed_at.desc())  # type: ignore[arg-type]
        ).all()
        for observation in observations:
            latest_observation_by_intent.setdefault(observation.intent_id, observation)

    primary_keyword_by_intent: dict[uuid.UUID, str] = {}
    for intent_id, links in links_by_intent.items():
        primary = next((keyword_by_id.get(link.keyword_id) for link in links if link.is_primary), None)
        if primary:
            primary_keyword_by_intent[intent_id] = primary.text
    primary_texts = list(set(primary_keyword_by_intent.values()))
    latest_execution_by_keyword: dict[str, SerpExecution] = {}
    if primary_texts:
        executions = session.exec(
            select(SerpExecution)
            .join(ResearchRun, SerpExecution.research_run_id == ResearchRun.id)  # type: ignore[arg-type]
            .where(ResearchRun.store_id == store_id)
            .where(SerpExecution.keyword.in_(primary_texts))  # type: ignore[union-attr]
            .order_by(SerpExecution.created_at.desc())  # type: ignore[arg-type]
        ).all()
        for execution in executions:
            latest_execution_by_keyword.setdefault(execution.keyword, execution)

    items: list[IntentListItem] = []
    for intent in intents:
        keywords = [
            IntentKeywordItem(text=keyword_by_id[link.keyword_id].text, is_primary=link.is_primary)
            for link in links_by_intent.get(intent.id, [])
            if link.keyword_id in keyword_by_id
        ]
        primary_keyword_text = primary_keyword_by_intent.get(intent.id)
        latest_observation = latest_observation_by_intent.get(intent.id)
        latest_execution = latest_execution_by_keyword.get(primary_keyword_text) if primary_keyword_text else None
        search_status = "measured" if latest_observation else "failed" if latest_execution and latest_execution.status.value == "error" else "not_tested"

        items.append(
            IntentListItem(
                id=intent.id,
                topic=intent.topic,
                category=intent.category,
                commercial_stage=intent.commercial_stage.value if intent.commercial_stage else None,
                estimated_demand=intent.estimated_demand.value if intent.estimated_demand else None,
                confidence=intent.confidence,
                source=intent.source.value,
                keywords=keywords,
                client_rank=latest_observation.client_rank if latest_observation else None,
                client_url=latest_observation.client_url if latest_observation else None,
                search_status=search_status,
                search_results_count=len(latest_observation.results) if latest_observation else None,
                search_observed_at=_iso_utc(latest_observation.observed_at) if latest_observation else None,
                search_country=latest_observation.country if latest_observation else None,
                search_device=latest_observation.device if latest_observation else None,
                search_engine=latest_observation.engine if latest_observation else None,
            )
        )

    return IntentListResponse(intents=items)


@router.get("/{store_id}/intent-clusters", response_model=IntentClusterListResponse)
def list_intent_clusters(store_id: uuid.UUID, session: Session = Depends(get_session)) -> IntentClusterListResponse:
    """Part Q1 — clusters from the latest research_run only (unlike
    /intents, which is all-time): a cluster's identity isn't stable across
    runs the way StableIntent is, so mixing clusters from different runs
    would just be confusing, not more complete."""
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    latest_run = _latest_pipeline_run(session, store_id)
    if latest_run is None:
        return IntentClusterListResponse(clusters=[])

    clusters = session.exec(
        select(IntentCluster)
        .where(IntentCluster.research_run_id == latest_run.id)
        .order_by(IntentCluster.intent_count.desc())  # type: ignore[arg-type]
    ).all()

    items: list[IntentClusterItem] = []
    for cluster in clusters:
        members = session.exec(select(Intent).where(Intent.cluster_id == cluster.id)).all()
        items.append(
            IntentClusterItem(
                id=cluster.id,
                label=cluster.label,
                category=cluster.category,
                intent_count=cluster.intent_count,
                intent_topics=[m.topic for m in members],
            )
        )

    return IntentClusterListResponse(clusters=items)


@router.get("/{store_id}/ai-visibility", response_model=AIVisibilityListResponse)
def list_ai_visibility(store_id: uuid.UUID, session: Session = Depends(get_session)) -> AIVisibilityListResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    latest_run = _latest_pipeline_run(session, store_id)

    unavailable_surfaces = unavailable_surface_names(get_settings())

    if latest_run is None:
        return AIVisibilityListResponse(
            summary=AIVisibilitySummary(total_observations=0, mention_rate=0.0, intent_coverage=0.0, citation_rate=0.0, stability=0.0),
            unavailable_surfaces=unavailable_surfaces,
        )

    metrics = compute_ai_visibility_metrics(session, latest_run.id)
    summary = AIVisibilitySummary(
        total_observations=metrics.total_observations,
        mention_rate=metrics.mention_rate,
        intent_coverage=metrics.intent_coverage,
        citation_rate=metrics.citation_rate,
        stability=metrics.stability,
    )

    surface_capabilities = {
        s.surface: s
        for s in AI_VISIBILITY_SURFACES
    }
    by_surface = [
        SurfaceMetrics(
            surface=surface,
            total_observations=m.total_observations,
            mention_rate=m.mention_rate,
            intent_coverage=m.intent_coverage,
            citation_rate=m.citation_rate,
            stability=m.stability,
            search_enabled=surface_capabilities[surface].search_enabled if surface in surface_capabilities else False,
            grounding_enabled=surface_capabilities[surface].grounding_enabled if surface in surface_capabilities else False,
        )
        for surface, m in compute_ai_visibility_metrics_by_surface(session, latest_run.id).items()
    ]

    observations = session.exec(
        select(AIVisibilityObservation)
        .where(AIVisibilityObservation.research_run_id == latest_run.id)
        .order_by(AIVisibilityObservation.observed_at.desc())  # type: ignore[arg-type]
    ).all()

    items: list[AIVisibilityObservationItem] = []
    storage = get_storage()
    for obs in observations:
        intent = session.get(Intent, obs.intent_id)
        variant = session.get(PromptVariant, obs.prompt_variant_id)
        response_text = None
        if obs.raw_artifact_uri:
            try:
                response_text = storage.get_text(obs.raw_artifact_uri)
            except Exception:
                # A missing historical artifact must not hide the structured
                # observation or turn the whole visibility page into an error.
                response_text = None
        items.append(
            AIVisibilityObservationItem(
                id=obs.id,
                intent_topic=intent.topic if intent else "",
                prompt_text=variant.text if variant else "",
                surface=obs.surface or obs.provider,
                provider=obs.provider,
                model=obs.model,
                search_enabled=obs.search_enabled,
                grounding_enabled=obs.grounding_enabled,
                citations_available=obs.citations_available,
                repetition_index=obs.repetition_index,
                observed_at=obs.observed_at,
                mentioned=obs.mentioned,
                mention_position=obs.mention_position,
                competitors_mentioned=obs.competitors_mentioned,
                products_mentioned=obs.products_mentioned,
                citations=obs.citations,
                linked_domains=obs.linked_domains,
                cited_domains=obs.cited_domains,
                response_text=response_text,
            )
        )

    return AIVisibilityListResponse(
        summary=summary, by_surface=by_surface, unavailable_surfaces=unavailable_surfaces, observations=items
    )


@router.get("/{store_id}/cross-surface-visibility", response_model=CrossSurfaceVisibilityResponse)
def get_cross_surface_visibility(store_id: uuid.UUID, session: Session = Depends(get_session)) -> CrossSurfaceVisibilityResponse:
    """Part F.5-9 — per stable intent, store vs competitor visibility across
    every surface (Google + each configured AI surface) in one view."""
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    latest_run = _latest_pipeline_run(session, store_id)
    unavailable_surfaces = unavailable_surface_names(get_settings())
    if latest_run is None:
        return CrossSurfaceVisibilityResponse(intents=[], unavailable_surfaces=unavailable_surfaces)

    rows = compute_cross_surface_visibility(session, latest_run.id)
    return CrossSurfaceVisibilityResponse(
        intents=[
            CrossSurfaceIntentItem(
                stable_intent_id=r.stable_intent_id,
                topic=r.topic,
                store_visibility=r.store_visibility,
                competitor_visibility=r.competitor_visibility,
                competitor_classifications=r.competitor_classifications,
            )
            for r in rows
        ],
        unavailable_surfaces=unavailable_surfaces,
    )


@router.get("/{store_id}/cost-summary", response_model=CostSummaryResponse)
def get_cost_summary(store_id: uuid.UUID, session: Session = Depends(get_session)) -> CostSummaryResponse:
    """Part F.5-12 — usage/cost for the latest research run, broken out by
    surface (Google + each AI surface), from the existing ai_executions/
    serp_executions ledgers."""
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    latest_run = _latest_pipeline_run(session, store_id)
    unavailable_surfaces = unavailable_surface_names(get_settings())
    if latest_run is None:
        return CostSummaryResponse(
            google=SurfaceUsageItem(surface="google", requests=0, cost_usd=0.0), ai_surfaces=[],
            unavailable_surfaces=unavailable_surfaces, other_ai_cost_usd=0.0, total_cost_usd=0.0,
        )

    summary = compute_cost_summary(session, latest_run.id)
    return CostSummaryResponse(
        google=SurfaceUsageItem(
            surface="google", requests=summary.google.requests, cost_usd=summary.google.cost_usd,
        ),
        ai_surfaces=[
            SurfaceUsageItem(
                surface=u.surface, requests=u.requests, input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                cost_usd=u.cost_usd,
            )
            for u in summary.ai_surfaces.values()
        ],
        unavailable_surfaces=unavailable_surfaces,
        other_ai_cost_usd=summary.other_ai_cost_usd,
        total_cost_usd=summary.total_cost_usd,
    )


@router.get("/{store_id}/competitors", response_model=CompetitorListResponse)
def list_competitors(store_id: uuid.UUID, session: Session = Depends(get_session)) -> CompetitorListResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    latest_run = _latest_pipeline_run(session, store_id)
    if latest_run is None:
        return CompetitorListResponse(competitors=[])

    rankings = compute_competitor_rankings(session, latest_run.id)
    items = [
        CompetitorListItem(
            id=r.competitor_id,
            domain=r.domain,
            name=r.name,
            competitor_type=r.competitor_type.value,
            serp_appearances=r.serp_appearances,
            avg_serp_rank=r.avg_serp_rank,
            ai_citation_count=r.ai_citation_count,
            classification=r.classification,
            relevance_score=r.relevance_score,
            classification_confidence=r.classification_confidence,
            discovery_reason=r.discovery_reason,
            shared_stable_intents_count=r.shared_stable_intents_count,
            is_business_competitor=r.classification == "direct_competitor",
        )
        for r in rankings
    ]
    return CompetitorListResponse(
        competitors=items,
        direct_competitor_count=sum(1 for i in items if i.is_business_competitor),
        visibility_only_count=sum(1 for i in items if not i.is_business_competitor),
    )


@router.post("/{store_id}/competitors/{competitor_id}/confirmation", response_model=SuggestedCompetitorItem)
def confirm_suggested_competitor(
    store_id: uuid.UUID, competitor_id: uuid.UUID, payload: CompetitorConfirmationRequest,
    session: Session = Depends(get_session),
) -> SuggestedCompetitorItem:
    """Phase 4/6 — a human acting on one of the identity-based competitor
    suggestions surfaced in get_store_understanding. Once a user has acted,
    the status is never overwritten again by a later discovery run (see
    discover_competitors' own auto-confirm guard, which only ever touches a
    competitor still at the default pending_user_confirmation)."""
    competitor = session.get(Competitor, competitor_id)
    if competitor is None or competitor.store_id != store_id:
        raise HTTPException(status_code=404, detail="competitor not found")
    if payload.action not in ("confirm", "reject"):
        raise HTTPException(status_code=422, detail="action must be 'confirm' or 'reject'")

    competitor.confirmation_status = "user_confirmed" if payload.action == "confirm" else "user_rejected"
    if payload.action == "confirm" and competitor.classification == "unknown":
        competitor.classification = "direct_competitor"
    session.add(competitor)
    session.commit()
    session.refresh(competitor)

    return SuggestedCompetitorItem(
        id=competitor.id, domain=competitor.domain, name=competitor.name,
        confirmation_status=competitor.confirmation_status,
        classification_confidence=competitor.classification_confidence,
        discovery_reason=competitor.discovery_reason,
    )


@router.get("/{store_id}/onboarding-summary", response_model=OnboardingSummaryResponse)
def get_onboarding_summary(store_id: uuid.UUID, session: Session = Depends(get_session)) -> OnboardingSummaryResponse:
    """Read-only aggregation over data the pipeline already measured this
    run — Intent + SerpObservation + CompetitorRelationship — no new AI or
    SERP calls, no re-derivation of scoring/recommendation logic that lives
    elsewhere. Built for the /signup onboarding wizard's result/competitors/
    market steps, which need a real 'X of Y' comparison basis rather than
    two unrelated aggregate stats."""
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    products_found = session.exec(select(func.count()).select_from(Product).where(Product.store_id == store_id)).one()
    categories_found = session.exec(
        select(func.count()).select_from(Category).where(Category.store_id == store_id)
    ).one()

    latest_run = _latest_pipeline_run(session, store_id)
    if latest_run is None:
        return OnboardingSummaryResponse(
            measured_count=0, sample_size=0, store_sample_appearances=0,
            products_found=products_found, categories_found=categories_found,
        )

    accepted_intents = session.exec(
        select(Intent)
        .where(Intent.store_id == store_id)
        .where(Intent.is_accepted == True)  # noqa: E712
        .order_by(Intent.created_at.desc())  # type: ignore[arg-type]
    ).all()
    intent_ids = [i.id for i in accepted_intents]

    latest_observation_by_intent: dict[uuid.UUID, SerpObservation] = {}
    if intent_ids:
        observations = session.exec(
            select(SerpObservation)
            .where(SerpObservation.intent_id.in_(intent_ids))  # type: ignore[union-attr]
            .order_by(SerpObservation.observed_at.desc())  # type: ignore[arg-type]
        ).all()
        for observation in observations:
            latest_observation_by_intent.setdefault(observation.intent_id, observation)

    measured_intents = [i for i in accepted_intents if i.id in latest_observation_by_intent]
    measured_count = len(measured_intents)

    stage_totals: dict[str, dict[str, int]] = {}
    ranked_values: list[int] = []
    for intent in measured_intents:
        observation = latest_observation_by_intent[intent.id]
        stage = intent.commercial_stage.value if intent.commercial_stage else "unknown"
        bucket = stage_totals.setdefault(stage, {"measured": 0, "top10": 0})
        bucket["measured"] += 1
        if observation.client_rank is not None:
            ranked_values.append(observation.client_rank)
            if observation.client_rank <= 10:
                bucket["top10"] += 1
    stage_breakdown = [
        OnboardingStageMetric(stage=stage, measured=counts["measured"], top10=counts["top10"])
        for stage, counts in stage_totals.items()
    ]
    best_rank = min(ranked_values) if ranked_values else None

    # Same fixed sample used both for the store-vs-competitor "X of Y"
    # comparison and the market step's sample search list, so the two
    # numbers the wizard shows are always about the same underlying queries.
    sample_intents_models = measured_intents[:10]
    sample_intent_ids = {i.id for i in sample_intents_models}
    sample_size = len(sample_intents_models)
    store_sample_appearances = sum(
        1
        for i in sample_intents_models
        if (obs := latest_observation_by_intent[i.id]).client_rank is not None and obs.client_rank <= 10
    )

    relationships = (
        session.exec(
            select(CompetitorRelationship)
            .where(CompetitorRelationship.research_run_id == latest_run.id)
            .where(CompetitorRelationship.source == RelationshipSource.serp)
        ).all()
        if latest_run
        else []
    )
    intent_stage_by_id = {i.id: (i.commercial_stage.value if i.commercial_stage else None) for i in accepted_intents}

    by_competitor: dict[uuid.UUID, list[CompetitorRelationship]] = {}
    for rel in relationships:
        by_competitor.setdefault(rel.competitor_id, []).append(rel)

    rankings = compute_competitor_rankings(session, latest_run.id)
    top_competitors: list[OnboardingCompetitorSummary] = []
    for ranking in rankings[:5]:
        rels = by_competitor.get(ranking.competitor_id, [])
        # A domain can rank with more than one page for the same intent's
        # SERP, producing multiple relationship rows for one intent — count
        # distinct intents, not raw rows, or "X of Y" can exceed Y.
        distinct_intent_ids = {r.intent_id for r in rels}
        sample_appearances = len(distinct_intent_ids & sample_intent_ids)

        stage_counts: dict[str, int] = {}
        for intent_id in distinct_intent_ids:
            stage = intent_stage_by_id.get(intent_id)
            if stage:
                stage_counts[stage] = stage_counts.get(stage, 0) + 1
        stronger_stage = None
        if stage_counts:
            top_stage, top_count = max(stage_counts.items(), key=lambda kv: kv[1])
            others = sum(c for s, c in stage_counts.items() if s != top_stage)
            if top_count >= 2 and top_count > others:
                stronger_stage = top_stage

        top_competitors.append(
            OnboardingCompetitorSummary(
                domain=ranking.domain,
                name=ranking.name,
                serp_appearances=ranking.serp_appearances,
                sample_appearances=sample_appearances,
                stronger_stage=stronger_stage,
            )
        )

    # Re-sort by the same sample-based count the wizard displays, so the
    # table's order always matches the numbers shown in it (compute_competitor_
    # rankings above orders by a broader relevance mix, not this one metric).
    top_competitors.sort(key=lambda c: c.sample_appearances, reverse=True)

    relationships_by_intent: dict[uuid.UUID, list[CompetitorRelationship]] = {}
    for rel in relationships:
        relationships_by_intent.setdefault(rel.intent_id, []).append(rel)
    competitor_by_id = {c.competitor_id: c for c in rankings}

    sample_intents: list[OnboardingSampleIntent] = []
    for intent in sample_intents_models:
        observation = latest_observation_by_intent[intent.id]
        intent_rels = sorted(
            relationships_by_intent.get(intent.id, []),
            key=lambda r: r.rank_or_position if r.rank_or_position is not None else 999,
        )
        top_rel = intent_rels[0] if intent_rels else None
        top_competitor = competitor_by_id.get(top_rel.competitor_id) if top_rel else None
        sample_intents.append(
            OnboardingSampleIntent(
                topic=intent.topic,
                commercial_stage=intent.commercial_stage.value if intent.commercial_stage else None,
                client_rank=observation.client_rank,
                top_competitor_domain=top_competitor.domain if top_competitor else None,
                top_competitor_name=top_competitor.name if top_competitor else None,
                top_competitor_rank=top_rel.rank_or_position if top_rel else None,
            )
        )

    # AI-visibility — a fully separate measurement (different provider,
    # different probed intents, its own cap) from the Google/SERP numbers
    # above. Never blended together; the frontend labels each by source.
    ai_observations = session.exec(
        select(AIVisibilityObservation).where(AIVisibilityObservation.research_run_id == latest_run.id)
    ).all()
    ai_by_intent: dict[uuid.UUID, list[AIVisibilityObservation]] = {}
    for observation in ai_observations:
        ai_by_intent.setdefault(observation.intent_id, []).append(observation)
    ai_measured_intent_ids = [i.id for i in accepted_intents if i.id in ai_by_intent]
    ai_measured_count = len(ai_measured_intent_ids)
    ai_sample_ids = ai_measured_intent_ids[:10]
    ai_sample_size = len(ai_sample_ids)
    ai_store_sample_appearances = sum(1 for iid in ai_sample_ids if any(o.mentioned for o in ai_by_intent[iid]))

    return OnboardingSummaryResponse(
        measured_count=measured_count,
        sample_size=sample_size,
        store_sample_appearances=store_sample_appearances,
        best_rank=best_rank,
        stage_breakdown=stage_breakdown,
        top_competitors=top_competitors,
        sample_intents=sample_intents,
        products_found=products_found,
        categories_found=categories_found,
        ai_measured_count=ai_measured_count,
        ai_sample_size=ai_sample_size,
        ai_store_sample_appearances=ai_store_sample_appearances,
    )


@router.post("/{store_id}/onboarding-lead", response_model=OnboardingLeadResponse, status_code=status.HTTP_201_CREATED)
def create_onboarding_lead(
    store_id: uuid.UUID, payload: OnboardingLeadRequest, session: Session = Depends(get_session)
) -> OnboardingLeadResponse:
    """Real persistence for the /signup wizard's final 'join the trial'
    step — tied to the store just analyzed and its latest run, if any."""
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    name = payload.name.strip()
    contact = payload.contact.strip()
    if not name or not contact:
        raise HTTPException(status_code=422, detail="name and contact are required")

    latest_run = _latest_pipeline_run(session, store_id)
    lead = OnboardingLead(
        store_id=store_id,
        research_run_id=latest_run.id if latest_run else None,
        name=name,
        contact=contact,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)

    return OnboardingLeadResponse(
        id=lead.id, store_id=lead.store_id, name=lead.name, contact=lead.contact, created_at=_iso_utc(lead.created_at)
    )


@router.get("/{store_id}/page-gaps", response_model=PageGapListResponse)
def list_page_gaps(store_id: uuid.UUID, session: Session = Depends(get_session)) -> PageGapListResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    latest_run = _latest_pipeline_run(session, store_id)
    if latest_run is None:
        return PageGapListResponse(page_gaps=[])

    analyses = session.exec(
        select(PageGapAnalysis)
        .where(PageGapAnalysis.research_run_id == latest_run.id)
        .order_by(PageGapAnalysis.created_at.desc())  # type: ignore[arg-type]
    ).all()

    items: list[PageGapItem] = []
    for analysis in analyses:
        intent = session.get(Intent, analysis.intent_id)
        competitor = session.get(Competitor, analysis.competitor_id)
        items.append(
            PageGapItem(
                id=analysis.id,
                intent_topic=intent.topic if intent else "",
                competitor_domain=competitor.domain if competitor else "",
                competitor_url=analysis.competitor_url,
                gaps=analysis.gaps,
                recommendation_summary=analysis.recommendation_summary,
                confidence=analysis.confidence,
            )
        )

    return PageGapListResponse(page_gaps=items)


@router.get("/{store_id}/research-tasks", response_model=ResearchTaskListResponse)
def list_research_tasks(store_id: uuid.UUID, session: Session = Depends(get_session)) -> ResearchTaskListResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    latest_run = _latest_pipeline_run(session, store_id)
    if latest_run is None:
        return ResearchTaskListResponse(tasks=[])

    tasks = session.exec(
        select(ResearchTask)
        .where(ResearchTask.research_run_id == latest_run.id)
        .order_by(ResearchTask.depth.asc(), ResearchTask.created_at.asc())  # type: ignore[arg-type]
    ).all()

    items = [
        ResearchTaskItem(
            id=t.id,
            parent_task_id=t.parent_task_id,
            task_type=t.task_type.value,
            status=t.status.value,
            depth=t.depth,
            priority=t.priority,
            reason=t.reason,
            hypothesis=t.hypothesis,
            result_summary=t.result_summary,
            discovered_entities=t.discovered_entities,
            created_tasks_count=t.created_tasks_count,
            cost=t.cost,
        )
        for t in tasks
    ]
    return ResearchTaskListResponse(tasks=items)


@router.get("/{store_id}/findings", response_model=FindingListResponse)
def list_findings(store_id: uuid.UUID, session: Session = Depends(get_session)) -> FindingListResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    latest_run = _latest_pipeline_run(session, store_id)
    if latest_run is None:
        return FindingListResponse(findings=[])

    findings = session.exec(
        select(Finding)
        .where(Finding.research_run_id == latest_run.id)
        .order_by(Finding.confidence.desc())  # type: ignore[arg-type]
    ).all()

    items = [
        FindingItem(
            id=f.id,
            finding_type=f.finding_type,
            statement=f.statement,
            confidence=f.confidence,
            status=f.status.value,
            validation_count=f.validation_count,
            affected_competitors=f.affected_competitors,
            affected_intents=f.affected_intents,
        )
        for f in findings
    ]
    return FindingListResponse(findings=items)


@router.get("/{store_id}/opportunities", response_model=OpportunityListResponse)
def list_opportunities(store_id: uuid.UUID, session: Session = Depends(get_session)) -> OpportunityListResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    opportunities = session.exec(
        select(Opportunity)
        .where(Opportunity.store_id == store_id)
        .order_by(Opportunity.priority_score.desc())  # type: ignore[arg-type]
    ).all()

    items = [
        OpportunityItem(
            id=o.id,
            opportunity_type=o.opportunity_type,
            title=o.title,
            description=o.description,
            priority_score=o.priority_score,
            score_breakdown=o.score_breakdown,
            confidence=o.confidence,
            effort_estimate=o.effort_estimate,
            status=o.status.value,
            affected_intents=o.affected_intents,
            competitors=o.competitors,
        )
        for o in opportunities
    ]
    return OpportunityListResponse(opportunities=items)


@router.get("/{store_id}/recommendations", response_model=RecommendationListResponse)
def list_recommendations(store_id: uuid.UUID, session: Session = Depends(get_session)) -> RecommendationListResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    # Beta Readiness Remediation, Section 3 — needs_validation recommendations
    # (evidence lost or never sufficient) are an internal research signal,
    # never customer-visible at all, not even in the general/backlog list.
    # Excluding the status here (rather than only from the primary-queue
    # selection) is what makes "NO EVIDENCE → NO RECOMMENDATION" apply to
    # every customer-facing surface, not just the "do this now" picks.
    recommendations = session.exec(
        select(Recommendation)
        .options(defer(Recommendation.page_id), defer(Recommendation.product_id))
        .where(Recommendation.store_id == store_id)
        .where(Recommendation.status != RecommendationStatus.needs_validation)
        .order_by(Recommendation.priority_score.desc())  # type: ignore[arg-type]
    ).all()

    settings = get_settings()
    # Primary queue (Part E8, freshness-gated since Part R2): top-N by
    # priority_score among status="new" recommendations the store's most
    # recent completed run actually reconfirmed — never a recommendation
    # only an older run touched (that is exactly what let Round 1's
    # extra.com show pre-fix garbage recommendations as if they were
    # current-run output).
    primary_ids = {r.id for r in select_primary_recommendations(session, store_id, settings.recommendation_primary_queue_size)}
    latest_run_id = latest_completed_research_run_id(session, store_id)

    opportunity_types = {
        o.id: o.opportunity_type
        for o in session.exec(
            select(Opportunity).where(Opportunity.id.in_({r.opportunity_id for r in recommendations}))  # type: ignore[attr-defined]
        ).all()
    }

    items = [
        RecommendationItem(
            id=r.id,
            opportunity_id=r.opportunity_id,
            opportunity_type=opportunity_types.get(r.opportunity_id, ""),
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
        )
        for r in recommendations
    ]
    return RecommendationListResponse(recommendations=items)


@router.get("/{store_id}/alerts", response_model=AlertListResponse)
def list_alerts(store_id: uuid.UUID, session: Session = Depends(get_session)) -> AlertListResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    alerts = session.exec(
        select(Alert).where(Alert.store_id == store_id).order_by(Alert.created_at.desc())  # type: ignore[arg-type]
    ).all()

    items = [
        AlertItem(
            id=a.id,
            alert_type=a.alert_type,
            severity=a.severity,
            title=a.title,
            message=a.message,
            status=a.status.value,
            related_recommendation_id=a.related_recommendation_id,
            related_competitor_id=a.related_competitor_id,
            created_at=a.created_at.isoformat(),
        )
        for a in alerts
    ]
    return AlertListResponse(alerts=items)
