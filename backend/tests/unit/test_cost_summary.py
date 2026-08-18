from app.models.ai_execution import AIExecution, AIExecutionStatus
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.serp import SerpExecution, SerpExecutionStatus
from app.models.store import Store
from app.research.cost_summary import compute_cost_summary


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-cost-summary")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    return store, run


def test_compute_cost_summary_splits_by_surface_and_totals_everything(session):
    store, run = _make_store_and_run(session)

    # ChatGPT surface (openai/gpt-4o-mini) — 2 ai_visibility_probe calls
    for _ in range(2):
        session.add(
            AIExecution(
                research_run_id=run.id, provider="openai", model="gpt-4o-mini", task_type="ai_visibility_probe",
                input_hash="h1", input_tokens=10, output_tokens=5, cost_usd=0.01, status=AIExecutionStatus.success,
            )
        )
    # Claude surface (anthropic/claude-haiku-4-5-20251001) — 1 call
    session.add(
        AIExecution(
            research_run_id=run.id, provider="anthropic", model="claude-haiku-4-5-20251001",
            task_type="ai_visibility_probe", input_hash="h2", input_tokens=8, output_tokens=4, cost_usd=0.02,
            status=AIExecutionStatus.success,
        )
    )
    # Non-visibility AI call (classification) — should land in other_ai_cost_usd, not a surface
    session.add(
        AIExecution(
            research_run_id=run.id, provider="openai", model="gpt-4o-mini", task_type="classification",
            input_hash="h3", input_tokens=20, output_tokens=10, cost_usd=0.03, status=AIExecutionStatus.success,
        )
    )
    session.add(
        SerpExecution(
            research_run_id=run.id, provider="serpapi", keyword="k", country="sa", language="ar", cost_usd=0.005,
            status=SerpExecutionStatus.success,
        )
    )
    session.commit()

    summary = compute_cost_summary(session, run.id)

    assert summary.google.requests == 1
    assert summary.google.cost_usd == 0.005
    assert summary.ai_surfaces["chatgpt"].requests == 2
    assert summary.ai_surfaces["chatgpt"].cost_usd == 0.02
    assert summary.ai_surfaces["claude"].requests == 1
    assert summary.ai_surfaces["claude"].cost_usd == 0.02
    assert summary.other_ai_cost_usd == 0.03
    assert round(summary.total_cost_usd, 5) == round(0.005 + 0.02 + 0.02 + 0.03, 5)


def test_compute_cost_summary_empty_run_returns_zeros(session):
    store, run = _make_store_and_run(session)
    summary = compute_cost_summary(session, run.id)
    assert summary.google.requests == 0
    assert summary.ai_surfaces == {}
    assert summary.total_cost_usd == 0.0
