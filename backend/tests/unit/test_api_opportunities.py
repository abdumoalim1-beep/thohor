import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.main as main_module
import app.models  # noqa: F401 — registers all tables
from app.core.db import get_session
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.finding import Finding, FindingStatus
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationHistory, RecommendationStatus
from app.models.research import ResearchRun, RunStatus
from app.models.store import Store
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelRouter


class ImplementationProvider(AIProvider):
    name = "openai"

    async def generate(self, request: AIRequest) -> AIResponse:
        output = {
            "summary": "مسودة مبنية على الدليل",
            "changes": [{"field": "H1", "current": None, "proposed": "دليل القهوة", "reason": "يغطي النية المرصودة"}],
            "title": "دليل القهوة",
            "meta_description": "دليل عملي",
            "h1": "دليل القهوة",
            "h2_sections": ["الأنواع"],
            "faq": [],
            "internal_links": [],
            "draft": "مسودة قابلة للمراجعة",
            "developer_instructions": [],
            "content_instructions": [],
            "assumptions_requiring_confirmation": ["أكد سياسة الشحن"],
        }
        return AIResponse(provider=self.name, model=request.model, text=json.dumps(output), usage=AIUsage(input_tokens=20, output_tokens=30))


@pytest.fixture()
def db_session():
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(test_engine)

    def override_get_session():
        with Session(test_engine) as session:
            yield session

    main_module.app.dependency_overrides[get_session] = override_get_session
    with Session(test_engine) as session:
        yield session
    main_module.app.dependency_overrides.clear()


@pytest.fixture()
def client(db_session):
    return TestClient(main_module.app)


def _seed(session):
    org = Organization(name="t", slug="t-api-opportunities")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://roastinghouse.sa")
    session.add(store)
    session.commit()
    session.refresh(store)
    from app.models.base import utcnow

    run = ResearchRun(store_id=store.id, status=RunStatus.completed, completed_at=utcnow())
    session.add(run)
    session.commit()
    session.refresh(run)

    evidence = Evidence(
        store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.page_gap_analysis,
        source_id=store.id, confidence=0.7, summary="raw evidence",
    )
    session.add(evidence)
    session.commit()
    session.refresh(evidence)

    finding = Finding(
        store_id=store.id, research_run_id=run.id, finding_type="dominant_competitor",
        statement="rival.test dominates", confidence=0.6, status=FindingStatus.candidate,
    )
    session.add(finding)
    session.commit()
    session.refresh(finding)

    opportunities = []
    recommendations = []
    for i in range(3):
        opp = Opportunity(
            store_id=store.id, research_run_id=run.id, opportunity_type="missing_landing_page",
            title=f"opp-{i}", description="d", finding_ids=[str(finding.id)],
            priority_score=90.0 - i * 10, status=OpportunityStatus.open, fingerprint=f"opp-fp-{i}",
        )
        session.add(opp)
        session.commit()
        session.refresh(opp)
        opportunities.append(opp)

        rec = Recommendation(
            store_id=store.id, opportunity_id=opp.id, first_seen_research_run_id=run.id,
            last_seen_research_run_id=run.id, title=f"rec-{i}", what_to_do="do", why_it_matters="why",
            evidence_ids=[str(evidence.id)], priority_score=90.0 - i * 10,
            # Beta Readiness Remediation — primary queue also requires
            # expected_impact >= PRIMARY_MIN_EXPECTED_IMPACT (0.4); this
            # test is about primary-queue *marking*, not commercial
            # relevance, so give it a value that clears the gate.
            expected_impact=0.7,
            status=RecommendationStatus.new, fingerprint=f"rec-fp-{i}",
        )
        session.add(rec)
        session.commit()
        session.refresh(rec)
        session.add(
            RecommendationHistory(recommendation_id=rec.id, research_run_id=run.id, event_type="created", snapshot={})
        )
        session.commit()
        recommendations.append(rec)

    return store, opportunities, recommendations


def test_list_opportunities_sorted_by_priority(client, db_session):
    store, opportunities, _ = _seed(db_session)
    response = client.get(f"/stores/{store.id}/opportunities")
    assert response.status_code == 200
    body = response.json()["opportunities"]
    assert len(body) == 3
    assert body[0]["priority_score"] >= body[1]["priority_score"] >= body[2]["priority_score"]


def test_list_recommendations_marks_primary_queue(client, db_session, monkeypatch):
    from app.core.config import Settings

    monkeypatch.setattr("app.api.stores.get_settings", lambda: Settings(recommendation_primary_queue_size=2))

    store, _, recommendations = _seed(db_session)
    response = client.get(f"/stores/{store.id}/recommendations")
    assert response.status_code == 200
    body = response.json()["recommendations"]
    primary = [r for r in body if r["is_primary"]]
    assert len(primary) == 2
    assert primary[0]["priority_score"] >= primary[1]["priority_score"]
    assert all(r["freshness"] == "current" for r in primary)


def test_stale_recommendation_never_shown_as_primary_over_the_api(client, db_session):
    """Part R2 — the exact extra.com bug, proven through the real API
    response the frontend Overview page reads: a recommendation last
    confirmed by an older run must never be primary once a newer run has
    completed, even if that newer run found nothing at all."""
    store, run_a, recommendations = _seed(db_session)

    run_b = ResearchRun(store_id=store.id, status=RunStatus.completed)
    from app.models.base import utcnow

    run_b.completed_at = utcnow()
    db_session.add(run_b)
    db_session.commit()

    response = client.get(f"/stores/{store.id}/recommendations")
    assert response.status_code == 200
    body = response.json()["recommendations"]
    assert len(body) == 3
    assert all(r["is_primary"] is False for r in body)  # Run B reconfirmed none of them
    assert all(r["freshness"] == "stale" for r in body)


def test_get_recommendation_returns_detail(client, db_session):
    _, _, recommendations = _seed(db_session)
    rec_id = recommendations[0].id
    response = client.get(f"/recommendations/{rec_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "rec-0"
    assert body["opportunity_type"] == "missing_landing_page"


def test_get_recommendation_resolves_competitor_references_to_domain_and_classification(client, db_session):
    """Part R6 — Recommendation.competitors_reference stores raw competitor
    UUIDs (recommendation_engine.py); the API must resolve them to
    something a user can read (domain + business-relevance classification),
    never leak a bare UUID into the response the frontend renders."""
    from app.models.competitor import Competitor, CompetitorType

    store, _, recommendations = _seed(db_session)
    publisher = Competitor(
        store_id=store.id, domain="ar.wikipedia.org", name="ar.wikipedia.org",
        competitor_type=CompetitorType.search_competitor, first_seen_research_run_id=recommendations[0].first_seen_research_run_id,
        classification="publisher", classification_confidence=0.9,
    )
    db_session.add(publisher)
    db_session.commit()
    db_session.refresh(publisher)

    rec = recommendations[0]
    rec.competitors_reference = [str(publisher.id)]
    db_session.add(rec)
    db_session.commit()

    response = client.get(f"/recommendations/{rec.id}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["competitors_reference"]) == 1
    ref = body["competitors_reference"][0]
    assert ref["domain"] == "ar.wikipedia.org"
    assert ref["classification"] == "publisher"
    assert ref["is_business_competitor"] is False


def test_patch_recommendation_status_updates_and_records_history(client, db_session):
    _, _, recommendations = _seed(db_session)
    rec_id = recommendations[0].id

    response = client.patch(
        f"/recommendations/{rec_id}/status",
        json={"status": "implemented", "implementation_url": "https://roastinghouse.sa/new-page"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "implemented"
    assert body["implementation_url"] == "https://roastinghouse.sa/new-page"
    assert body["implemented_at"] is not None


def test_patch_recommendation_status_rejects_invalid_status(client, db_session):
    _, _, recommendations = _seed(db_session)
    rec_id = recommendations[0].id
    response = client.patch(f"/recommendations/{rec_id}/status", json={"status": "not_a_real_status"})
    assert response.status_code == 422


def test_get_recommendation_evidence_returns_full_trace(client, db_session):
    _, _, recommendations = _seed(db_session)
    rec_id = recommendations[0].id
    response = client.get(f"/recommendations/{rec_id}/evidence")
    assert response.status_code == 200
    body = response.json()
    assert body["opportunity"] is not None
    assert len(body["findings"]) == 1
    assert len(body["evidence"]) == 1


def test_get_implementation_package(client, db_session):
    _, _, recommendations = _seed(db_session)
    rec_id = recommendations[0].id
    response = client.get(f"/recommendations/{rec_id}/implementation-package")
    assert response.status_code == 200
    assert "implementation_package" in response.json()


def test_generate_implementation_runs_only_on_post_and_persists_output(client, db_session, monkeypatch):
    _, _, recommendations = _seed(db_session)
    rec = recommendations[0]
    router = ModelRouter(providers={"openai": ImplementationProvider()})
    monkeypatch.setattr("app.workers.tasks.engine", db_session.get_bind())
    monkeypatch.setattr("app.workers.tasks.get_router", lambda: router)
    monkeypatch.setattr("app.api.recommendations.execute_implementation_generation_task.delay", lambda store_id, run_id: __import__("app.workers.tasks", fromlist=["execute_implementation_generation_task"]).execute_implementation_generation_task.run(store_id, run_id))

    response = client.post(f"/recommendations/{rec.id}/generate-implementation", json={"mode": "rebuild"})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    job = client.get(f"/stores/{rec.store_id}/on-demand-analyses/{body['research_run_id']}/status").json()
    assert job["status"] == "completed"
    assert job["result"]["output"]["changes"][0]["field"] == "H1"
    db_session.refresh(rec)
    assert rec.implementation_package["on_demand"]["rebuild"]["summary"] == "مسودة مبنية على الدليل"
    history = db_session.exec(
        select(RecommendationHistory).where(RecommendationHistory.recommendation_id == rec.id)
    ).all()
    assert any(item.event_type == "implementation_generated" for item in history)


def test_recommendation_404_for_unknown_id(client):
    response = client.get("/recommendations/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
