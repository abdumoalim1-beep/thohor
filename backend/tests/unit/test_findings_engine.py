from sqlmodel import select

from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.finding import Finding, FindingStatus
from app.models.intent import Intent, IntentSource
from app.models.opportunity import Opportunity
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.research_task import ResearchTask, TaskStatus, TaskType
from app.models.store import Store
from app.research.findings_engine import backfill_task_opportunity_impact, extract_findings_from_market_map


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-findings-engine")
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


def _make_intent(session, store, run, topic):
    intent = Intent(
        store_id=store.id,
        research_run_id=run.id,
        topic=topic,
        country="sa",
        language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    return intent


def _make_competitor(session, store, run, domain, classification="direct_competitor"):
    competitor = Competitor(
        store_id=store.id,
        domain=domain,
        name=domain,
        competitor_type=CompetitorType.search_competitor,
        first_seen_research_run_id=run.id,
        classification=classification,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)
    return competitor


def test_extracts_dominant_competitor_finding_when_thresholds_met(session):
    store, run = _make_store_and_run(session)
    competitor = _make_competitor(session, store, run, "dominant.test")

    for i in range(3):
        intent = _make_intent(session, store, run, f"topic-{i}")
        session.add(
            CompetitorRelationship(
                competitor_id=competitor.id,
                intent_id=intent.id,
                research_run_id=run.id,
                source=RelationshipSource.serp,
                rank_or_position=1,
            )
        )
    session.commit()

    findings = extract_findings_from_market_map(session, store.id, run.id)

    assert len(findings) == 1
    assert findings[0].finding_type == "dominant_competitor"
    assert findings[0].status == FindingStatus.supported
    assert findings[0].evidence_breakdown["store"]["checked"] is True
    assert findings[0].affected_competitors == [str(competitor.id)]

    persisted = session.exec(select(Finding).where(Finding.research_run_id == run.id)).all()
    assert len(persisted) == 1


def test_no_finding_when_appearances_below_threshold(session):
    store, run = _make_store_and_run(session)
    competitor = _make_competitor(session, store, run, "weak.test")
    intent = _make_intent(session, store, run, "topic")
    session.add(
        CompetitorRelationship(
            competitor_id=competitor.id,
            intent_id=intent.id,
            research_run_id=run.id,
            source=RelationshipSource.serp,
            rank_or_position=1,
        )
    )
    session.commit()

    findings = extract_findings_from_market_map(session, store.id, run.id)
    assert findings == []


def test_no_finding_when_avg_rank_too_weak(session):
    store, run = _make_store_and_run(session)
    competitor = _make_competitor(session, store, run, "midrank.test")
    for i in range(3):
        intent = _make_intent(session, store, run, f"topic-{i}")
        session.add(
            CompetitorRelationship(
                competitor_id=competitor.id,
                intent_id=intent.id,
                research_run_id=run.id,
                source=RelationshipSource.serp,
                rank_or_position=8,
            )
        )
    session.commit()

    findings = extract_findings_from_market_map(session, store.id, run.id)
    assert findings == []


def test_does_not_duplicate_finding_for_same_competitor_across_calls(session):
    store, run = _make_store_and_run(session)
    competitor = _make_competitor(session, store, run, "dominant.test")
    for i in range(3):
        intent = _make_intent(session, store, run, f"topic-{i}")
        session.add(
            CompetitorRelationship(
                competitor_id=competitor.id,
                intent_id=intent.id,
                research_run_id=run.id,
                source=RelationshipSource.serp,
                rank_or_position=1,
            )
        )
    session.commit()

    first_call = extract_findings_from_market_map(session, store.id, run.id)
    second_call = extract_findings_from_market_map(session, store.id, run.id)

    assert len(first_call) == 1
    assert second_call == []
    persisted = session.exec(select(Finding).where(Finding.research_run_id == run.id)).all()
    assert len(persisted) == 1


def test_backfill_task_opportunity_impact_traces_finding_back_to_its_task(session):
    store, run = _make_store_and_run(session)
    competitor = _make_competitor(session, store, run, "dominant.test")
    for i in range(3):
        intent = _make_intent(session, store, run, f"topic-{i}")
        session.add(
            CompetitorRelationship(
                competitor_id=competitor.id,
                intent_id=intent.id,
                research_run_id=run.id,
                source=RelationshipSource.serp,
                rank_or_position=1,
            )
        )
    session.commit()

    task = ResearchTask(
        research_run_id=run.id,
        store_id=store.id,
        task_type=TaskType.competitor_discovery_batch,
        status=TaskStatus.completed,
        depth=0,
        fingerprint="seed-task",
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    findings = extract_findings_from_market_map(session, store.id, run.id, origin_task_id=task.id)
    assert findings[0].origin_task_id == task.id

    opportunity = Opportunity(
        store_id=store.id,
        research_run_id=run.id,
        opportunity_type="dominant_competitor_follow_up",
        title="t",
        description="d",
        finding_ids=[str(findings[0].id)],
        fingerprint="opp-1",
    )
    session.add(opportunity)
    session.commit()

    backfill_task_opportunity_impact(session, run.id, [opportunity])

    session.refresh(task)
    assert task.affected_opportunities_count == 1


def test_backfill_task_opportunity_impact_is_a_noop_with_no_opportunities(session):
    store, run = _make_store_and_run(session)
    backfill_task_opportunity_impact(session, run.id, [])  # must not raise
