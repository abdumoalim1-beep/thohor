from app.evaluation.campaign_cost_report import compute_campaign_cost_report
from app.models.ai_execution import AIExecution
from app.models.evaluation import EvaluationCampaign
from app.models.finding import Finding, FindingStatus
from app.models.opportunity import Opportunity
from app.models.org import Organization
from app.models.recommendation import Recommendation
from app.models.research import ResearchRun
from app.models.serp import SerpExecution
from app.models.store import Store


def _make_store_and_run(session, org_slug="t-cost-report"):
    org = Organization(name="t", slug=org_slug)
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


def test_compute_campaign_cost_report_aggregates_real_usage(session):
    store, run = _make_store_and_run(session)

    campaign = EvaluationCampaign(
        name="FINAL_VALIDATION_1", allocated_serp_budget=250, used_serp_requests=30, stores=[str(store.id)]
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    session.add(
        AIExecution(
            research_run_id=run.id, provider="openai", model="gpt-4o-mini", task_type="ai_visibility_probe",
            input_hash="test-hash", input_tokens=100, output_tokens=50, cost_usd=0.01,
        )
    )
    session.add(
        SerpExecution(research_run_id=run.id, provider="serpapi", keyword="k", country="sa", language="ar", cost_usd=0.02)
    )
    session.add(
        Finding(
            store_id=store.id, research_run_id=run.id, finding_type="dominant_competitor", statement="s",
            status=FindingStatus.supported,
        )
    )
    opportunity = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="google_visibility_gap",
        title="t", description="d", fingerprint="opp-fp-1",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    session.add(
        Recommendation(
            store_id=store.id, opportunity_id=opportunity.id, first_seen_research_run_id=run.id,
            last_seen_research_run_id=run.id, title="t", what_to_do="d", why_it_matters="w", fingerprint="fp-1",
        )
    )
    session.commit()

    report = compute_campaign_cost_report(session, campaign.id)

    assert report.campaign_name == "FINAL_VALIDATION_1"
    assert report.serp_requests_used == 30
    assert report.serp_budget_remaining == 220
    assert report.openai_requests == 1
    assert report.openai_tokens == 150
    assert round(report.openai_cost_usd, 4) == 0.01
    assert round(report.total_cost_usd, 4) == 0.03
    assert report.store_count == 1
    assert round(report.cost_per_store, 4) == 0.03
    assert round(report.cost_per_useful_finding, 4) == 0.03
    assert round(report.cost_per_recommendation, 4) == 0.03


def test_compute_campaign_cost_report_handles_no_stores_yet(session):
    campaign = EvaluationCampaign(name="FINAL_VALIDATION_1", allocated_serp_budget=250, stores=[])
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    report = compute_campaign_cost_report(session, campaign.id)

    assert report.store_count == 0
    assert report.cost_per_store is None
    assert report.cost_per_useful_finding is None
    assert report.cost_per_recommendation is None
    assert report.total_cost_usd == 0.0
