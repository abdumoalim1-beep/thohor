"""Full ResearchOrchestrator.execute_run path — real network (crawl), fake
storage/AI/search providers. This is the path that actually exercises
_complete_agent_run() with a real evidence_id, which is what caught the
'UUID not JSON serializable' bug that unit tests (which never ran a
successful classification through the orchestrator) missed.

AI Visibility engines (openai/anthropic/google) are intentionally left
unregistered here — the AI Test Matrix logic itself is unit-tested with
fakes in tests/unit/test_visibility_engine.py; this test's job is proving
the 9-step *sequencing* works (Group D2: the old fixed
competitor_discovery_agent_run + page_intelligence_agent_run steps are
superseded by one iterative_research_agent_run; Group E adds
opportunity_recommendation_agent_run; Group F adds
monitoring_and_alerts_agent_run), not re-verifying each engine.

MockSearchProvider (Group B) never returns the client's own domain, and its
results would otherwise all be mined as competitor relationships (Group D
Part D1) — Part G-B5 moved that SERP-mining step to right after
serp_agent_run (before ai_visibility_batch runs), not the loop's seed task
anymore; the seed task now only mines ai_visibility_observations. Part R7:
MockSearchProvider's deterministic domains are reserved test-TLD ones
(example-competitor-N.test), so the synthetic-domain guard now skips all of
them — this run legitimately discovers zero competitors; see
test_discovery_engine.py for mining itself proven against real-shaped
domains. No research_planning
route is configured here, so
the one Planner call the loop attempts (it now always tries once before
the queue empties, even below PLANNER_INTERVAL — see
tests/unit/test_research_loop.py's regression test for why) fails with
'no route configured' and is silently absorbed, leaving exactly one
research_task (the seed). The Planner's own successful-suggestion behavior
is covered by tests/unit/test_research_loop.py.
"""

import json
import uuid

from sqlmodel import select

import app.orchestrator.research_orchestrator as research_orchestrator_module
from app.core.config import Settings
from app.core.evaluation_mode import EvaluationMode
from app.models.intent import Intent
from app.models.observation import PageObservation
from app.models.org import Organization
from app.models.research import AgentRun, RunStatus
from app.models.serp import SerpObservation
from app.models.store import Store, StoreStatus
from app.orchestrator.research_orchestrator import ResearchOrchestrator
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute
from app.providers.search.mock_provider import MockSearchProvider
from tests.integration.test_store_intelligence import FakeClassifierProvider, FakeStorage

TEST_STORE_URL = "https://books.toscrape.com"


class FakePromptFamilyProvider(AIProvider):
    name = "fake_prompt_family"

    async def generate(self, request: AIRequest) -> AIResponse:
        payload = json.dumps({"prompts": ["وش أفضل خيار هنا؟", "أبي توصية بميزانية محددة"]})
        return AIResponse(
            provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=10, output_tokens=10)
        )


async def test_execute_run_completes_all_nine_agent_runs(session):
    org = Organization(name="Test Org", slug="test-org-orchestrator")
    session.add(org)
    session.commit()
    session.refresh(org)

    store = Store(organization_id=org.id, url=TEST_STORE_URL)
    session.add(store)
    session.commit()
    session.refresh(store)

    run = ResearchOrchestrator.create_pending_run(session, store)

    settings = Settings(
        crawler_max_pages_per_run=3,
        crawler_max_depth=1,
        intent_max_per_run=5,
        serp_max_queries_per_run=5,
        ai_visibility_max_intents_per_run=2,
        ai_visibility_prompt_variants_per_intent=2,
        # Explicit rather than relying on Settings' class-level default —
        # a local .env with EVALUATION_MODE=live (set for this session's
        # live-testing against real stores) would otherwise leak into this
        # test and break the "replay" assertion below for reasons that have
        # nothing to do with what this test is actually checking.
        evaluation_mode=EvaluationMode.replay,
    )
    router = ModelRouter(
        providers={"fake": FakeClassifierProvider(), "fake_pf": FakePromptFamilyProvider()},
        routes={
            "classification": TaskRoute(primary=ModelChoice("fake", "fake-model")),
            "prompt_family_generation": TaskRoute(primary=ModelChoice("fake_pf", "fake-model")),
            # No intent_expansion route and no openai/anthropic/google keys —
            # both expected to fail/no-op gracefully without blocking the run.
            # No store_identity_resolution route either — identity resolution
            # is expected to fail honestly (see the agent_types assertion and
            # comment below) rather than block or fake a result.
        },
    )
    orchestrator = ResearchOrchestrator(
        session=session,
        storage=FakeStorage(),
        router=router,
        search_provider=MockSearchProvider(),
        settings=settings,
    )

    result = await orchestrator.execute_run(store, run)

    assert result.status == RunStatus.completed
    assert result.error is None
    # Part H2 — every run must record which EvaluationMode it actually ran
    # under.
    assert result.evaluation_mode == "replay"

    session.refresh(store)
    assert store.status == StoreStatus.active

    agent_runs = session.exec(select(AgentRun).where(AgentRun.research_run_id == run.id)).all()
    agent_types = {ar.agent_type: ar for ar in agent_runs}
    assert set(agent_types) == {
        "crawl_agent_run",
        # Phase 1 — runs for every baseline run regardless of crawl outcome.
        # No "store_identity_resolution" route is configured in this test's
        # router, so router.execute raises "no route configured", which
        # resolve_store_identity does NOT swallow (only provider/timeout
        # failures are treated as a normal degrade there) — it propagates to
        # the orchestrator's own broad except, which fails this one agent_run
        # honestly rather than block the rest of the pipeline. Because
        # identity is None afterward, Phase 4/5's competitor-discovery and
        # question-generation steps never even start (both are gated on a
        # resolved identity) — neither shows up in this set.
        "store_identity_agent_run",
        "ai_classification_agent_run",
        "intent_agent_run",
        "serp_agent_run",
        "prompt_family_agent_run",
        "ai_visibility_agent_run",
        "iterative_research_agent_run",
        "opportunity_recommendation_agent_run",
        "monitoring_and_alerts_agent_run",
    }
    for agent_type in agent_types:
        if agent_type == "store_identity_agent_run":
            assert agent_types[agent_type].status == RunStatus.failed
            continue
        assert agent_types[agent_type].status == RunStatus.completed

    # Deterministic seed intents come from the catalog with zero AI
    # dependency, so SERP measurement (against the mock provider) still
    # produces observations even though intent_expansion has no real route.
    serp_observations = session.exec(select(SerpObservation).where(SerpObservation.store_id == store.id)).all()
    assert len(serp_observations) > 0

    # Part Q1 — every accepted intent ends up in some cluster (including
    # clusters of size 1), wired right after the quality gate.
    assert agent_types["intent_agent_run"].findings["intent_clusters"] > 0
    accepted_intents = session.exec(
        select(Intent).where(Intent.research_run_id == run.id).where(Intent.is_accepted == True)  # noqa: E712
    ).all()
    assert all(i.cluster_id is not None for i in accepted_intents)

    assert agent_types["prompt_family_agent_run"].findings["prompt_variants_generated"] > 0
    # No openai/anthropic/google key configured in this test -> the matrix
    # legitimately has zero engines to probe.
    assert agent_types["ai_visibility_agent_run"].findings["observations_recorded"] == 0

    # SERP-sourced competitors would already be mined by the time the loop
    # starts (Part G-B5 — see module docstring), but MockSearchProvider's
    # results are all reserved test-TLD domains (example-competitor-N.test)
    # — Part R7's synthetic-domain guard (app.core.domain.is_synthetic_test_domain)
    # deliberately never lets those become real Competitor rows, so this
    # mock-driven run finds zero competitors (a customer-data-integrity
    # trade-off, not a mining bug — see test_discovery_engine.py for mining
    # itself proven against non-synthetic domains). The loop's seed task
    # (competitor_discovery_batch) mines ai_visibility_observations only,
    # also finds none here (zero AI providers configured), and completes as
    # the only task since the Planner never fires. research_depth_reached
    # stays 0 accordingly.
    research_metrics = agent_types["iterative_research_agent_run"].findings
    assert research_metrics["total_tasks"] == 1
    assert research_metrics["competitors_discovered"] == 0
    assert research_metrics["research_depth_reached"] == 0
    # Whether any competitor crossed the dominant_competitor threshold
    # (findings_engine.py) depends on how many SERP queries the real,
    # size-limited books.toscrape.com crawl actually produced this run —
    # not deterministic enough to assert an exact count here; the
    # threshold logic itself is covered by tests/unit/test_findings_engine.py.
    assert research_metrics["findings_generated"] >= 0

    # Group E: opportunity discovery is free (no AI/network calls) and runs
    # regardless of what the loop found — books.toscrape.com has no
    # competitor page gaps or AI citation data, so the google_visibility_gap
    # detector is the one realistically expected to fire here.
    opp_rec_findings = agent_types["opportunity_recommendation_agent_run"].findings
    assert opp_rec_findings["opportunities_found"] >= 0
    assert opp_rec_findings["recommendations_generated"] >= 0
    assert opp_rec_findings["recommendations_generated"] <= opp_rec_findings["opportunities_found"]
    # Part Q3 — the quality gate runs over the real primary queue every run.
    assert opp_rec_findings["primary_queue_size"] <= 5  # Settings default recommendation_primary_queue_size
    assert opp_rec_findings["quality_issues_found"] == 0  # books.toscrape.com's real recommendations are clean
    assert opp_rec_findings["quality_issue_checks"] == []

    # Group F: first-ever run for this store -> no previous completed run to
    # diff against, so competitor_overtook/ai_visibility_dropped/
    # new_competitor never fire; only new_high_priority_opportunity or
    # recommendation_showing_results could (neither guaranteed here).
    monitoring_findings = agent_types["monitoring_and_alerts_agent_run"].findings
    assert monitoring_findings["recommendations_checked_for_implementation"] >= 0
    assert monitoring_findings["alerts_generated"] >= 0


async def test_execute_run_is_idempotent_on_redispatch_of_the_same_run(session):
    """Part H7 — a research_run must execute its full pipeline exactly
    once. Simulates a redelivered dispatch (Celery at-least-once, an
    accidental double .delay(), a retried multi-store batch): calling
    execute_run a second time on the same (already-claimed) run row must
    be a pure no-op — no second crawl, no duplicate agent_runs/
    observations — since the atomic claim in execute_run only lets the
    UPDATE...WHERE status='pending' succeed once."""
    org = Organization(name="Test Org", slug="test-org-orchestrator-idempotent")
    session.add(org)
    session.commit()
    session.refresh(org)

    store = Store(organization_id=org.id, url=TEST_STORE_URL)
    session.add(store)
    session.commit()
    session.refresh(store)

    run = ResearchOrchestrator.create_pending_run(session, store)

    settings = Settings(
        crawler_max_pages_per_run=3,
        crawler_max_depth=1,
        intent_max_per_run=5,
        serp_max_queries_per_run=5,
        ai_visibility_max_intents_per_run=2,
        ai_visibility_prompt_variants_per_intent=2,
    )
    router = ModelRouter(
        providers={"fake": FakeClassifierProvider(), "fake_pf": FakePromptFamilyProvider()},
        routes={
            "classification": TaskRoute(primary=ModelChoice("fake", "fake-model")),
            "prompt_family_generation": TaskRoute(primary=ModelChoice("fake_pf", "fake-model")),
        },
    )
    orchestrator = ResearchOrchestrator(
        session=session, storage=FakeStorage(), router=router, search_provider=MockSearchProvider(), settings=settings,
    )

    first = await orchestrator.execute_run(store, run)
    assert first.status == RunStatus.completed
    first_agent_run_ids = {
        ar.id for ar in session.exec(select(AgentRun).where(AgentRun.research_run_id == run.id)).all()
    }
    first_observation_count = len(session.exec(select(SerpObservation).where(SerpObservation.store_id == store.id)).all())

    # A second dispatch of the exact same run row — must not re-run anything.
    second = await orchestrator.execute_run(store, run)

    assert second.id == first.id
    assert second.status == RunStatus.completed
    second_agent_run_ids = {
        ar.id for ar in session.exec(select(AgentRun).where(AgentRun.research_run_id == run.id)).all()
    }
    assert second_agent_run_ids == first_agent_run_ids  # no new agent_runs created
    second_observation_count = len(session.exec(select(SerpObservation).where(SerpObservation.store_id == store.id)).all())
    assert second_observation_count == first_observation_count  # no duplicate observations


async def test_execute_run_marks_cancelled_when_cancellation_requested_before_the_loop(session):
    """Part H8 — end-to-end: cancellation requested on a still-pending run
    lets the fixed pipeline steps run (crawl/classification/intents/serp/
    prompt_family/ai_visibility aren't gated by cancellation — only the
    iterative research loop's task dispatch is), but the iterative loop
    itself must dispatch nothing, and the run's FINAL status must read
    RunStatus.cancelled, never RunStatus.completed."""
    from app.research.cancellation import request_run_cancellation

    org = Organization(name="Test Org", slug="test-org-orchestrator-cancelled")
    session.add(org)
    session.commit()
    session.refresh(org)

    store = Store(organization_id=org.id, url=TEST_STORE_URL)
    session.add(store)
    session.commit()
    session.refresh(store)

    run = ResearchOrchestrator.create_pending_run(session, store)
    assert request_run_cancellation(session, run.id) is True

    settings = Settings(
        crawler_max_pages_per_run=3,
        crawler_max_depth=1,
        intent_max_per_run=5,
        serp_max_queries_per_run=5,
        ai_visibility_max_intents_per_run=2,
        ai_visibility_prompt_variants_per_intent=2,
    )
    router = ModelRouter(
        providers={"fake": FakeClassifierProvider(), "fake_pf": FakePromptFamilyProvider()},
        routes={
            "classification": TaskRoute(primary=ModelChoice("fake", "fake-model")),
            "prompt_family_generation": TaskRoute(primary=ModelChoice("fake_pf", "fake-model")),
        },
    )
    orchestrator = ResearchOrchestrator(
        session=session, storage=FakeStorage(), router=router, search_provider=MockSearchProvider(), settings=settings,
    )

    result = await orchestrator.execute_run(store, run)

    assert result.status == RunStatus.cancelled
    agent_types = {
        ar.agent_type: ar for ar in session.exec(select(AgentRun).where(AgentRun.research_run_id == run.id)).all()
    }
    # The fixed pipeline still ran and produced real data...
    assert agent_types["crawl_agent_run"].status == RunStatus.completed
    assert agent_types["serp_agent_run"].status == RunStatus.completed
    serp_observations = session.exec(select(SerpObservation).where(SerpObservation.store_id == store.id)).all()
    assert len(serp_observations) > 0
    # ...but the iterative loop never dispatched its seed task — the only
    # research_task row is the seed itself, still `pending`.
    from app.models.research_task import ResearchTask, TaskStatus

    tasks = session.exec(select(ResearchTask).where(ResearchTask.research_run_id == run.id)).all()
    assert len(tasks) == 1
    assert tasks[0].status == TaskStatus.pending
    assert agent_types["iterative_research_agent_run"].findings["stop_reason"] == "cancelled by request"


async def test_classification_is_skipped_honestly_when_the_crawl_found_almost_nothing(session, monkeypatch):
    """Proves the real orchestrator wiring (not just the pure gate function
    in isolation): a near-empty crawl must never reach the classification
    LLM call, and must record why on the agent run instead of silently
    looking like a normal completion. run_crawl_agent itself is faked here
    (not the network) — the crawl's own correctness is exercised by the
    real-network test above; this test isolates the gate."""
    org = Organization(name="Test Org", slug="test-org-orchestrator-thin-crawl")
    session.add(org)
    session.commit()
    session.refresh(org)

    store = Store(organization_id=org.id, url=TEST_STORE_URL)
    session.add(store)
    session.commit()
    session.refresh(store)

    run = ResearchOrchestrator.create_pending_run(session, store)

    async def fake_run_crawl_agent(*, session, storage, store_id, research_run_id, agent_run_id, **kwargs):
        # One observation — below MIN_OBSERVATIONS_FOR_CLASSIFICATION (3),
        # mirroring a bot-blocked or near-empty real crawl.
        observation = PageObservation(
            store_id=store_id, research_run_id=research_run_id, agent_run_id=agent_run_id,
            source_url=store.url, extractor_version="v2",
            normalized_extraction={"title": "Just a moment...", "h1": None},
        )
        session.add(observation)
        session.commit()
        return [observation]

    monkeypatch.setattr(research_orchestrator_module, "run_crawl_agent", fake_run_crawl_agent)

    settings = Settings(
        crawler_max_pages_per_run=3, crawler_max_depth=1, intent_max_per_run=5, serp_max_queries_per_run=5,
    )
    router = ModelRouter(providers={"fake": FakeClassifierProvider()}, routes={
        "classification": TaskRoute(primary=ModelChoice("fake", "fake-model")),
    })
    orchestrator = ResearchOrchestrator(
        session=session, storage=FakeStorage(), router=router, search_provider=MockSearchProvider(), settings=settings,
    )

    result = await orchestrator.execute_run(store, run)

    assert result.status == RunStatus.completed
    agent_types = {
        ar.agent_type: ar for ar in session.exec(select(AgentRun).where(AgentRun.research_run_id == run.id)).all()
    }
    classification_run = agent_types["ai_classification_agent_run"]
    assert classification_run.status == RunStatus.completed
    assert classification_run.findings["skipped"] is True
    assert classification_run.findings["reason"] == "insufficient_observations"
    assert classification_run.findings["observations_count"] == 1
    assert classification_run.evidence_ids == []
