from datetime import timedelta

from sqlmodel import select

from app.evaluation.harness import compute_evaluation_summary
from app.models.ai_execution import AIExecution, AIExecutionStatus
from app.models.base import utcnow
from app.models.evaluation import EvaluationSummary
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.finding import Finding, FindingStatus
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import AgentRun, ResearchRun, RunStatus
from app.models.serp import SerpExecution, SerpExecutionStatus
from app.models.store import Store


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-eval-harness")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)

    now = utcnow()
    run = ResearchRun(
        store_id=store.id, status=RunStatus.completed, started_at=now, completed_at=now + timedelta(seconds=120)
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return store, run


def test_compute_evaluation_summary_aggregates_across_the_run(session):
    store, run = _make_store_and_run(session)

    session.add(
        AgentRun(research_run_id=run.id, agent_type="iterative_research_agent_run", status=RunStatus.completed,
                 findings={"stop_reason": "no pending tasks remaining"})
    )
    session.add(AgentRun(research_run_id=run.id, agent_type="crawl_agent_run", status=RunStatus.failed, error="boom"))
    session.commit()

    session.add(
        AIExecution(
            research_run_id=run.id, provider="openai", model="gpt-4o-mini", task_type="ai_visibility_probe",
            input_hash="h1", input_tokens=10, output_tokens=20, cost_usd=0.001, status=AIExecutionStatus.success,
            prompt_name="ai_visibility_probe", prompt_version="v1",
        )
    )
    session.add(
        SerpExecution(
            research_run_id=run.id, provider="serpapi", keyword="k", country="sa", language="ar", cost_usd=0.01,
            status=SerpExecutionStatus.success,
        )
    )
    session.commit()

    finding = Finding(
        store_id=store.id, research_run_id=run.id, finding_type="dominant_competitor", statement="s",
        confidence=0.8, status=FindingStatus.validated,
    )
    session.add(finding)
    session.commit()
    session.refresh(finding)

    opportunity = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="google_visibility_gap", title="t",
        description="d", status=OpportunityStatus.open, fingerprint="fp-eval-harness",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    evidence = Evidence(
        store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.serp_observation,
        source_id=opportunity.id, confidence=1.0, summary="e",
    )
    session.add(evidence)
    session.commit()
    session.refresh(evidence)

    recommendation = Recommendation(
        store_id=store.id, opportunity_id=opportunity.id, first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id, title="t", what_to_do="do", why_it_matters="why",
        status=RecommendationStatus.new, fingerprint="rec-fp-eval-harness", priority_score=90.0,
        evidence_ids=[str(evidence.id)],
        # Beta Readiness Remediation — primary queue also requires
        # expected_impact >= PRIMARY_MIN_EXPECTED_IMPACT (0.4).
        expected_impact=0.7,
    )
    session.add(recommendation)
    session.commit()

    summary = compute_evaluation_summary(session, run.id)

    assert summary.store_id == store.id
    assert summary.research_run_id == run.id
    assert summary.failures == 1
    assert summary.stop_reason == "no pending tasks remaining"
    assert summary.findings == 1
    assert summary.validated_findings == 1
    assert summary.opportunities == 1
    assert summary.recommendations == 1
    assert summary.primary_recommendations == 1  # only "new" recommendation, within primary queue size
    assert summary.ai_executions == 1
    assert summary.tokens == 30
    assert round(summary.cost_usd, 3) == 0.011
    assert summary.duration_seconds == 120.0
    assert summary.research_tasks == 0
    assert summary.research_yield is None  # validated_findings / research_tasks, but 0 research_tasks -> undefined
    assert summary.evidence_yield == 1.0  # the one evidence is referenced by the one recommendation
    assert summary.versions["prompt_versions"]["ai_visibility_probe"] == "v1"

    persisted = session.exec(select(EvaluationSummary).where(EvaluationSummary.research_run_id == run.id)).one()
    assert persisted.id == summary.id


def test_compute_evaluation_summary_is_idempotent_on_recompute(session):
    store, run = _make_store_and_run(session)
    first = compute_evaluation_summary(session, run.id)
    second = compute_evaluation_summary(session, run.id)

    assert first.id == second.id
    all_rows = session.exec(select(EvaluationSummary).where(EvaluationSummary.research_run_id == run.id)).all()
    assert len(all_rows) == 1


def test_compute_evaluation_summary_records_performance_metrics_from_iterative_run(session):
    """Part H2 — peak/average concurrency and sequential-vs-actual duration,
    as computed and stored by the loop itself (app.research.metrics), flow
    through into the persisted EvaluationSummary."""
    store, run = _make_store_and_run(session)
    session.add(
        AgentRun(
            research_run_id=run.id, agent_type="iterative_research_agent_run", status=RunStatus.completed,
            findings={
                "stop_reason": "no pending tasks remaining",
                "peak_concurrency": 3,
                "average_concurrency": 1.8,
                "sequential_time_estimate_seconds": 42.0,
                "actual_parallel_duration_seconds": 15.0,
            },
        )
    )
    session.commit()

    summary = compute_evaluation_summary(session, run.id)

    assert summary.peak_concurrency == 3
    assert summary.average_concurrency == 1.8
    assert summary.sequential_time_estimate_seconds == 42.0
    assert summary.actual_parallel_duration_seconds == 15.0


def test_compute_evaluation_summary_records_the_evaluation_mode_from_the_run(session):
    """Part H2 — a replay-sourced run's summary must be explicitly
    traceable as replay, never mistakable for a fresh live measurement."""
    store, run = _make_store_and_run(session)
    run.evaluation_mode = "replay"
    session.add(run)
    session.commit()

    summary = compute_evaluation_summary(session, run.id)

    assert summary.evaluation_mode == "replay"
