from app.models.evidence import Evidence, EvidenceSourceType
from app.models.finding import Finding, FindingStatus
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import ResearchRun
from app.models.store import Store
from app.opportunities.evidence_trace import trace_recommendation_evidence


def test_trace_recommendation_evidence_walks_full_chain(session):
    org = Organization(name="t", slug="t-evidence-trace")
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

    opportunity = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="missing_landing_page",
        title="t", description="d", finding_ids=[str(finding.id)], status=OpportunityStatus.open,
        fingerprint="opp-fp",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    recommendation = Recommendation(
        store_id=store.id, opportunity_id=opportunity.id, first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id, title="t", what_to_do="do", why_it_matters="why",
        evidence_ids=[str(evidence.id)], status=RecommendationStatus.new, fingerprint="rec-fp",
    )
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)

    trace = trace_recommendation_evidence(session, recommendation.id)

    assert trace is not None
    assert trace["recommendation"].id == recommendation.id
    assert trace["opportunity"].id == opportunity.id
    assert len(trace["findings"]) == 1
    assert trace["findings"][0].id == finding.id
    assert len(trace["evidence"]) == 1
    assert trace["evidence"][0].id == evidence.id


def test_trace_recommendation_evidence_returns_none_for_unknown_id(session):
    import uuid

    assert trace_recommendation_evidence(session, uuid.uuid4()) is None
