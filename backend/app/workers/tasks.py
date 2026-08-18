import asyncio
import uuid

from sqlmodel import Session

from app.ai_visibility.multi_engine_runner import create_pending_visibility_run
from app.ai_visibility.visibility_orchestration import run_visibility_measurement
from app.models.visibility_run import VisibilityRun
from app.core.config import get_settings
from app.core.db import engine
from app.core.storage import get_storage
from app.models.recommendation import Recommendation
from app.models.research import AgentRun, ResearchRun, ResearchRunType, RunStatus
from app.models.store import Store
from app.orchestrator.research_orchestrator import ResearchOrchestrator
from app.providers.ai import get_router
from app.providers.search import get_search_provider
from app.services.on_demand_jobs import (
    execute_implementation_generation,
    execute_market_exploration,
    execute_winning_page_analysis,
    mark_failed,
)
from app.workers.celery_app import celery_app
from app.workers.scheduling import dispatch_due_stores, dispatch_due_visibility_stores


@celery_app.task(name="research.execute_run")
def execute_research_run_task(store_id: str, research_run_id: str, campaign_id: str | None = None) -> str:
    """Execution layer only. All sequencing/dependency logic lives in
    ResearchOrchestrator — this task just runs it inside a Celery worker and
    owns nothing else, so swapping Celery for another executor later doesn't
    touch orchestration logic. Operates on the research_run row the API
    already created (via ResearchOrchestrator.create_pending_run), never a
    new one.

    campaign_id (optional, Part H3) — when set, live SerpAPI requests are
    wrapped in CampaignGuardedSearchProvider so the run can never exceed a
    reserved evaluation campaign's allocated budget. Ordinary product usage
    (API-triggered onboarding, scheduled runs) never passes this and is
    unaffected; it exists so a reserved live-validation round can safely
    dispatch through the real Celery execution path instead of an ad-hoc
    script.
    """
    settings = get_settings()

    with Session(engine) as session:
        store = session.get(Store, uuid.UUID(store_id))
        if store is None:
            raise ValueError(f"store {store_id} not found")

        run = session.get(ResearchRun, uuid.UUID(research_run_id))
        if run is None:
            raise ValueError(f"research_run {research_run_id} not found")

        orchestrator = ResearchOrchestrator(
            session=session,
            storage=get_storage(),
            router=get_router(),
            search_provider=get_search_provider(session, campaign_id=uuid.UUID(campaign_id) if campaign_id else None),
            settings=settings,
        )
        run = asyncio.run(orchestrator.execute_run(store, run))
        if run.run_type == ResearchRunType.baseline and run.status == RunStatus.completed:
            # 90-search re-scope — visibility analysis is no longer
            # auto-dispatched here. It must start only after the user sees
            # their store identity and explicitly clicks "متابعة" on
            # /signup, which calls POST /stores/{id}/visibility-runs (the
            # endpoint already guards against a duplicate concurrent run).
            # The baseline run completing still question-generates in the
            # background (question_generation runs inside the orchestrator
            # itself, unaffected) so those questions are ready the moment
            # the user clicks continue.
            expansion = ResearchOrchestrator.create_pending_run(session, store, ResearchRunType.verification)
            execute_research_run_task.delay(str(store.id), str(expansion.id))
        return str(run.id)


@celery_app.task(name="research.scan_scheduled")
def scan_and_dispatch_scheduled_runs() -> int:
    """Group F7 — Celery beat calls this periodically (see beat_schedule in
    celery_app.py). All the 'who's due, create the run, advance the
    schedule' logic lives in dispatch_due_stores (execution-layer-free,
    fully testable); this task's only job is enqueuing execution for each
    one, same division of responsibility as execute_research_run_task."""
    with Session(engine) as session:
        dispatched = dispatch_due_stores(session)
        for store_id, run_id in dispatched:
            execute_research_run_task.delay(str(store_id), str(run_id))
        return len(dispatched)


@celery_app.task(name="visibility.scan_scheduled")
def scan_and_dispatch_scheduled_visibility_runs() -> int:
    """Weekly cadence — same division of responsibility as
    scan_and_dispatch_scheduled_runs (business logic in
    dispatch_due_visibility_stores, this task only enqueues execution)."""
    with Session(engine) as session:
        due = dispatch_due_visibility_stores(session)
        for store_id in due:
            execute_visibility_run_task.delay(str(store_id))
        return len(due)


@celery_app.task(name="visibility.run")
def execute_visibility_run_task(store_id: str, visibility_run_id: str | None = None) -> str:
    """Execution layer only, same division of responsibility as
    execute_research_run_task — all sequencing lives in
    run_visibility_measurement (runner + analysis), this just runs it
    inside a worker. visibility_run_id, when given, is a row the API
    endpoint already created (so its returned id stays the real one this
    task updates); omitted for the scheduled weekly dispatch path, which
    creates its own."""
    with Session(engine) as session:
        run = (
            session.get(VisibilityRun, uuid.UUID(visibility_run_id))
            if visibility_run_id is not None
            else create_pending_visibility_run(session, uuid.UUID(store_id))
        )
        if run is None:
            raise ValueError(f"visibility_run {visibility_run_id} not found")
        run, _analyses = asyncio.run(
            run_visibility_measurement(
                session=session, router=get_router(), run=run, search_provider=get_search_provider(session)
            )
        )
        return str(run.id)


def _load_job(session: Session, store_id: str, run_id: str, agent_type: str):
    store = session.get(Store, uuid.UUID(store_id))
    run = session.get(ResearchRun, uuid.UUID(run_id))
    if store is None or run is None or run.store_id != store.id:
        raise ValueError("on-demand job not found")
    from sqlmodel import select
    agent = session.exec(select(AgentRun).where(AgentRun.research_run_id == run.id).where(AgentRun.agent_type == agent_type)).first()
    if agent is None:
        raise ValueError("on-demand agent not found")
    return store, run, agent


@celery_app.task(name="on_demand.market_exploration")
def execute_market_exploration_task(store_id: str, run_id: str) -> str:
    with Session(engine) as session:
        store, run, agent = _load_job(session, store_id, run_id, "on_demand_market_exploration")
        request = (agent.findings or {}).get("request", {})
        try:
            asyncio.run(execute_market_exploration(session, store, run, agent, request["topic"], request["max_queries"], get_search_provider(session), get_settings()))
        except Exception as exc:  # noqa: BLE001 — persisted failure is the job contract
            mark_failed(session, run, agent, exc)
        return run_id


@celery_app.task(name="on_demand.winning_page_analysis")
def execute_winning_page_analysis_task(store_id: str, run_id: str) -> str:
    with Session(engine) as session:
        store, run, agent = _load_job(session, store_id, run_id, "on_demand_winning_page_analysis")
        try:
            asyncio.run(execute_winning_page_analysis(session, store, run, agent, (agent.findings or {})["request"], get_router(), get_settings()))
        except Exception as exc:  # noqa: BLE001 — persisted failure is the job contract
            mark_failed(session, run, agent, exc)
        return run_id


@celery_app.task(name="on_demand.implementation_generation")
def execute_implementation_generation_task(store_id: str, run_id: str) -> str:
    with Session(engine) as session:
        _, run, agent = _load_job(session, store_id, run_id, "on_demand_implementation_generation")
        request = (agent.findings or {}).get("request", {})
        recommendation = session.get(Recommendation, uuid.UUID(request["recommendation_id"]))
        if recommendation is None:
            mark_failed(session, run, agent, ValueError("recommendation not found"))
            return run_id
        try:
            asyncio.run(execute_implementation_generation(session, recommendation, run, agent, request["mode"], get_router()))
        except Exception as exc:  # noqa: BLE001 — persisted failure is the job contract
            mark_failed(session, run, agent, exc)
        return run_id
