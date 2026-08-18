import uuid

from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.intent import Intent, IntentSource
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.research.task_builder import resolve_task_input
from app.schemas.research_planning import NewTaskSuggestion


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-task-builder")
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


def test_resolve_competitor_deep_dive_finds_competitor_and_best_intent(session):
    store, run = _make_store_and_run(session)
    intent = Intent(
        store_id=store.id, research_run_id=run.id, topic="t", country="sa", language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    competitor = Competitor(
        store_id=store.id, domain="rival.test", name="rival.test",
        competitor_type=CompetitorType.search_competitor, first_seen_research_run_id=run.id,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)

    session.add(
        CompetitorRelationship(
            competitor_id=competitor.id, intent_id=intent.id, research_run_id=run.id,
            source=RelationshipSource.serp, rank_or_position=1,
        )
    )
    session.commit()

    suggestion = NewTaskSuggestion(
        task_type="competitor_deep_dive", target="Rival.Test", reason="r", priority=0.9
    )
    resolved = resolve_task_input(session, store.id, run.id, suggestion)

    assert resolved == {"competitor_id": str(competitor.id), "intent_id": str(intent.id)}


def test_resolve_competitor_deep_dive_returns_none_for_unknown_domain(session):
    store, run = _make_store_and_run(session)
    suggestion = NewTaskSuggestion(task_type="competitor_deep_dive", target="unknown.test", reason="r", priority=0.5)
    assert resolve_task_input(session, store.id, run.id, suggestion) is None


def test_resolve_query_expansion_extracts_id_tag(session):
    store, run = _make_store_and_run(session)
    intent_id = uuid.uuid4()
    suggestion = NewTaskSuggestion(
        task_type="query_expansion", target=f"id={intent_id}", reason="r", priority=0.5
    )
    resolved = resolve_task_input(session, store.id, run.id, suggestion)
    assert resolved == {"intent_id": str(intent_id)}


def test_resolve_validate_finding_extracts_id_tag(session):
    store, run = _make_store_and_run(session)
    finding_id = uuid.uuid4()
    suggestion = NewTaskSuggestion(
        task_type="validate_finding", target=f"id={finding_id}", reason="r", priority=0.5
    )
    resolved = resolve_task_input(session, store.id, run.id, suggestion)
    assert resolved == {"finding_id": str(finding_id)}


def test_resolve_query_expansion_returns_none_without_id_tag(session):
    store, run = _make_store_and_run(session)
    suggestion = NewTaskSuggestion(task_type="query_expansion", target="some vague text", reason="r", priority=0.5)
    assert resolve_task_input(session, store.id, run.id, suggestion) is None


def test_resolve_search_google_extracts_id_tag(session):
    store, run = _make_store_and_run(session)
    intent_id = uuid.uuid4()
    suggestion = NewTaskSuggestion(task_type="search_google", target=f"id={intent_id}", reason="r", priority=0.5)
    assert resolve_task_input(session, store.id, run.id, suggestion) == {"intent_id": str(intent_id)}


def test_resolve_ai_visibility_surface_task_types_extract_id_tag(session):
    store, run = _make_store_and_run(session)
    intent_id = uuid.uuid4()
    for task_type in ("ai_visibility_chatgpt", "ai_visibility_gemini", "ai_visibility_claude"):
        suggestion = NewTaskSuggestion(task_type=task_type, target=f"id={intent_id}", reason="r", priority=0.5)
        assert resolve_task_input(session, store.id, run.id, suggestion) == {"intent_id": str(intent_id)}


def test_resolve_validate_cross_surface_finding_extracts_id_tag(session):
    store, run = _make_store_and_run(session)
    finding_id = uuid.uuid4()
    suggestion = NewTaskSuggestion(
        task_type="validate_cross_surface_finding", target=f"id={finding_id}", reason="r", priority=0.5
    )
    assert resolve_task_input(session, store.id, run.id, suggestion) == {"finding_id": str(finding_id)}
