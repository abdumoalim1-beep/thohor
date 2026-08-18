import uuid
from collections import defaultdict

from sqlmodel import Session, func, select

from app.core.config import get_settings
from app.models.ai_execution import AIExecution
from app.models.ai_visibility import AIVisibilityObservation
from app.models.competitor import Competitor, CompetitorRelationship
from app.models.evaluation import EvaluationSummary
from app.models.evidence import Evidence
from app.models.finding import Finding, FindingStatus
from app.models.intent import Intent
from app.models.observation import PageObservation
from app.models.opportunity import Opportunity
from app.models.recommendation import Recommendation
from app.models.research import AgentRun, ResearchRun, RunStatus
from app.opportunities.freshness import select_primary_recommendations
from app.models.research_task import ResearchTask, TaskStatus
from app.models.serp import SerpExecution, SerpObservation
from app.models.store import Store


def _store_type(session: Session, store: Store, research_run_id: uuid.UUID) -> str | None:
    if store.platform_hint:
        return store.platform_hint
    classification_run = session.exec(
        select(AgentRun)
        .where(AgentRun.research_run_id == research_run_id)
        .where(AgentRun.agent_type == "ai_classification_agent_run")
    ).first()
    if classification_run and classification_run.findings:
        return classification_run.findings.get("business_type")
    return None


def compute_evaluation_summary(session: Session, research_run_id: uuid.UUID) -> EvaluationSummary:
    """Part G0 — Benchmark Harness. Reads exclusively from tables the
    research_orchestrator already writes; computing this never issues a
    new search/AI call and never mutates anything the product itself
    depends on. Safe to run against any completed (or failed) run,
    repeatedly, for before/after comparison across future Group G changes.
    """
    run = session.get(ResearchRun, research_run_id)
    if run is None:
        raise ValueError(f"research_run {research_run_id} not found")
    store = session.get(Store, run.store_id)
    if store is None:
        raise ValueError(f"store for research_run {research_run_id} not found")

    agent_runs = session.exec(select(AgentRun).where(AgentRun.research_run_id == research_run_id)).all()
    failures = sum(1 for a in agent_runs if a.status == RunStatus.failed)

    monitoring_agent_run = next((a for a in agent_runs if a.agent_type == "monitoring_and_alerts_agent_run"), None)
    iterative_agent_run = next((a for a in agent_runs if a.agent_type == "iterative_research_agent_run"), None)
    iterative_findings = (iterative_agent_run.findings or {}) if iterative_agent_run else {}
    stop_reason = iterative_findings.get("stop_reason", "")
    # Part H — ResearchMetrics (app/research/metrics.py) already computes
    # these from the loop's own research_task rows; the orchestrator stores
    # the whole dataclass on iterative_research_agent_run.findings, so this
    # is just reading it back out, same as stop_reason above.
    peak_concurrency = iterative_findings.get("peak_concurrency")
    average_concurrency = iterative_findings.get("average_concurrency")
    sequential_time_estimate_seconds = iterative_findings.get("sequential_time_estimate_seconds")
    actual_parallel_duration_seconds = iterative_findings.get("actual_parallel_duration_seconds")

    page_count = session.exec(
        select(func.count()).select_from(PageObservation).where(PageObservation.research_run_id == research_run_id)
    ).one()
    research_tasks = session.exec(
        select(func.count()).select_from(ResearchTask).where(ResearchTask.research_run_id == research_run_id)
    ).one()
    task_depth = session.exec(
        select(func.max(ResearchTask.depth)).where(ResearchTask.research_run_id == research_run_id)  # type: ignore[arg-type]
    ).one() or 0
    google_queries = session.exec(
        select(func.count()).select_from(SerpExecution).where(SerpExecution.research_run_id == research_run_id)
    ).one()
    chatgpt_prompts = session.exec(
        select(func.count())
        .select_from(AIVisibilityObservation)
        .where(AIVisibilityObservation.research_run_id == research_run_id)
    ).one()
    serp_observations = session.exec(
        select(func.count()).select_from(SerpObservation).where(SerpObservation.research_run_id == research_run_id)
    ).one()
    total_observations = serp_observations + chatgpt_prompts

    competitors_discovered = session.exec(
        select(func.count()).select_from(Competitor).where(Competitor.first_seen_research_run_id == research_run_id)
    ).one()

    # Part G-B2 — classification touched this run (every competitor with a
    # relationship this run gets reclassified, not just newly-discovered
    # ones — see app.competitors.classification).
    competitor_ids_this_run = session.exec(
        select(CompetitorRelationship.competitor_id)
        .where(CompetitorRelationship.research_run_id == research_run_id)
        .distinct()
    ).all()
    classified_competitors = (
        session.exec(select(Competitor).where(Competitor.id.in_(competitor_ids_this_run))).all()  # type: ignore[attr-defined]
        if competitor_ids_this_run
        else []
    )
    # Part R3 — the curated non-competitor categories expanded (wholesale,
    # forum, educational, ...); "irrelevant" here means "confirmed not a
    # business signal worth showing", which now spans every curated
    # category plus "unknown" (too little evidence either way) — but not
    # "retailer" (a genuine, if unconfirmed, visibility-relevant entity).
    _NOISE_CLASSIFICATIONS = frozenset(
        {"irrelevant", "unknown", "marketplace", "wholesale", "social", "forum", "video", "publisher", "government", "educational"}
    )
    competitor_direct_count = sum(1 for c in classified_competitors if c.classification == "direct_competitor")
    competitor_visibility_only_count = sum(1 for c in classified_competitors if c.classification != "direct_competitor")
    competitor_irrelevant_rate = (
        sum(1 for c in classified_competitors if c.classification in _NOISE_CLASSIFICATIONS)
        / len(classified_competitors)
        if classified_competitors
        else None
    )

    findings = session.exec(select(Finding).where(Finding.research_run_id == research_run_id)).all()
    validated_findings = sum(1 for f in findings if f.status == FindingStatus.validated)

    opportunities = session.exec(
        select(func.count()).select_from(Opportunity).where(Opportunity.research_run_id == research_run_id)
    ).one()

    run_recommendations = session.exec(
        select(Recommendation).where(Recommendation.last_seen_research_run_id == research_run_id)
    ).all()

    settings = get_settings()
    # Part R2 — evaluated *as of this specific run* (not "whatever the
    # store's latest run happens to be today"), since this summary can be
    # recomputed for an older run after newer ones already exist.
    primary_ids = {
        r.id
        for r in select_primary_recommendations(
            session, store.id, settings.recommendation_primary_queue_size, as_of_run_id=research_run_id
        )
    }
    primary_recommendations = sum(1 for r in run_recommendations if r.id in primary_ids)

    ai_executions_rows = session.exec(select(AIExecution).where(AIExecution.research_run_id == research_run_id)).all()
    ai_executions = len(ai_executions_rows)
    tokens = sum((e.input_tokens or 0) + (e.output_tokens or 0) for e in ai_executions_rows)
    serp_executions_rows = session.exec(
        select(SerpExecution).where(SerpExecution.research_run_id == research_run_id)
    ).all()
    cost_usd = sum(e.cost_usd or 0.0 for e in ai_executions_rows) + sum(
        e.cost_usd or 0.0 for e in serp_executions_rows
    )

    duration_seconds = (
        (run.completed_at - run.started_at).total_seconds() if run.started_at and run.completed_at else 0.0
    )

    research_yield = (validated_findings / research_tasks) if research_tasks else None

    total_evidence_this_run = session.exec(
        select(func.count()).select_from(Evidence).where(Evidence.research_run_id == research_run_id)
    ).one()
    evidence_used_by_recommendations = {eid for r in run_recommendations for eid in r.evidence_ids}
    evidence_yield = (
        (len(evidence_used_by_recommendations) / total_evidence_this_run) if total_evidence_this_run else None
    )

    # Part G-B — quality metrics.
    scored_intents = session.exec(select(Intent).where(Intent.research_run_id == research_run_id)).all()
    intent_acceptance_rate = (
        sum(1 for i in scored_intents if i.is_accepted) / len(scored_intents) if scored_intents else None
    )
    intent_duplicate_rate = (
        sum(1 for i in scored_intents if i.quality_reason and "near-duplicate" in i.quality_reason)
        / len(scored_intents)
        if scored_intents
        else None
    )

    finding_validation_rate = (validated_findings / len(findings)) if findings else None

    all_tasks = session.exec(select(ResearchTask).where(ResearchTask.research_run_id == research_run_id)).all()
    completed_tasks = [t for t in all_tasks if t.status == TaskStatus.completed]
    # Part G-B4 — `useful` is now persisted per-task by the loop itself
    # (app.research.loop) at the moment it completes, so this reads that
    # single source of truth instead of recomputing an independent
    # definition here. `useful is False` (not falsy) so a task whose
    # usefulness hasn't been evaluated for some other reason isn't silently
    # miscounted as a dead end.
    dead_end_tasks = sum(1 for t in completed_tasks if t.useful is False)
    dead_end_task_rate = (dead_end_tasks / len(completed_tasks)) if completed_tasks else None
    skipped_duplicate_tasks = sum(1 for t in all_tasks if t.status == TaskStatus.skipped_duplicate)
    duplicate_task_proposal_rate = (skipped_duplicate_tasks / len(all_tasks)) if all_tasks else None

    recommendation_evidence_coverage = (
        sum(1 for r in run_recommendations if r.evidence_ids) / len(run_recommendations)
        if run_recommendations
        else None
    )

    prompt_versions: dict[str, str] = {}
    for e in ai_executions_rows:
        if e.prompt_name:
            prompt_versions[e.prompt_name] = e.prompt_version or ""
    versions = {"scoring_version": "v1", "prompt_versions": prompt_versions}

    existing = session.exec(
        select(EvaluationSummary).where(EvaluationSummary.research_run_id == research_run_id)
    ).first()

    values = dict(
        store_id=store.id,
        research_run_id=research_run_id,
        store_url=store.url,
        store_type=_store_type(session, store, research_run_id),
        page_count=page_count,
        research_tasks=research_tasks,
        task_depth=task_depth,
        google_queries=google_queries,
        chatgpt_prompts=chatgpt_prompts,
        total_observations=total_observations,
        competitors_discovered=competitors_discovered,
        findings=len(findings),
        validated_findings=validated_findings,
        opportunities=opportunities,
        recommendations=len(run_recommendations),
        primary_recommendations=primary_recommendations,
        ai_executions=ai_executions,
        tokens=tokens,
        cost_usd=cost_usd,
        duration_seconds=duration_seconds,
        failures=failures,
        stop_reason=stop_reason,
        research_yield=research_yield,
        evidence_yield=evidence_yield,
        intent_acceptance_rate=intent_acceptance_rate,
        intent_duplicate_rate=intent_duplicate_rate,
        competitor_direct_count=competitor_direct_count,
        competitor_visibility_only_count=competitor_visibility_only_count,
        competitor_irrelevant_rate=competitor_irrelevant_rate,
        finding_validation_rate=finding_validation_rate,
        dead_end_task_rate=dead_end_task_rate,
        duplicate_task_proposal_rate=duplicate_task_proposal_rate,
        recommendation_evidence_coverage=recommendation_evidence_coverage,
        versions=versions,
        evaluation_mode=run.evaluation_mode,
        peak_concurrency=peak_concurrency,
        average_concurrency=average_concurrency,
        sequential_time_estimate_seconds=sequential_time_estimate_seconds,
        actual_parallel_duration_seconds=actual_parallel_duration_seconds,
    )

    if existing is not None:
        for key, value in values.items():
            setattr(existing, key, value)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    summary = EvaluationSummary(**values)
    session.add(summary)
    session.commit()
    session.refresh(summary)
    return summary
