import json

from sqlmodel import select

from app.competitors.discovery_engine import mine_serp_competitors
from app.core.config import Settings
from app.crawler.fetch import FetchResult
from app.intent.intent_engine import _attach_keywords
from app.models.ai_visibility import AIVisibilityObservation, PromptFamily, PromptVariant
from app.models.competitor import Competitor
from app.models.intent import Intent, IntentSource, Keyword
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.research_task import ResearchTask, TaskStatus, TaskType
from app.models.serp import SerpObservation
from app.models.store import Store
from app.page_intelligence import gap_engine as gap_engine_module
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute
from app.providers.search.base import SearchProvider, SearchRequest, SearchResponse
from app.research import loop as loop_module
from app.research.loop import run_iterative_research_loop

COMPETITOR_HTML = "<html><head><title>Grinder Guide</title></head><body><h1>Grinder Guide</h1></body></html>"


class FakePlannerProvider(AIProvider):
    name = "fake_planner"

    async def generate(self, request: AIRequest) -> AIResponse:
        payload = json.dumps(
            {
                "new_tasks": [
                    {
                        "task_type": "competitor_deep_dive",
                        "target": "rival.co",
                        "reason": "يظهر بقوة في هذه النية",
                        "hypothesis": None,
                        "priority": 0.9,
                    }
                ]
            }
        )
        return AIResponse(
            provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=10, output_tokens=10)
        )


class FakeGapProvider(AIProvider):
    name = "fake_gap"

    async def generate(self, request: AIRequest) -> AIResponse:
        payload = json.dumps(
            {"gaps": ["دليل شراء غير موجود عندنا"], "recommendation_summary": "أضف دليل شراء.", "confidence": 0.7}
        )
        return AIResponse(
            provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=10, output_tokens=10)
        )


class NullSearchProvider(SearchProvider):
    name = "null_search"

    async def search(self, request: SearchRequest) -> SearchResponse:
        return SearchResponse(provider=self.name, results=[])


class _FakeStorage:
    def put_text(self, key_prefix, content, content_type="text/html"):
        return f"s3://fake/{key_prefix}/key"


def _seed_store_with_serp_observation(session, with_ai_visibility_mention=False):
    org = Organization(name="t", slug="t-research-loop")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example", language="ar")
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)

    intent = Intent(
        store_id=store.id,
        research_run_id=run.id,
        topic="coffee grinder",
        country="sa",
        language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    _attach_keywords(session, intent, ["coffee grinder"], "sa", "ar")
    keyword = session.exec(select(Keyword)).one()

    session.add(
        SerpObservation(
            store_id=store.id,
            intent_id=intent.id,
            keyword_id=keyword.id,
            research_run_id=run.id,
            country="sa",
            language="ar",
            results=[{"rank": 1, "domain": "rival.co", "url": "https://rival.co/grinders"}],
            client_rank=None,
        )
    )
    session.commit()

    # Part G-B5: production now seeds SERP-sourced competitors right after
    # the serp_batch fixed phase, before the iterative loop even starts —
    # mirror that here so the loop's seed task (which now only mines
    # ai_visibility_observations) still finds "rival.co" already present.
    mine_serp_competitors(session, store.id, store.url, run.id)

    if with_ai_visibility_mention:
        family = PromptFamily(intent_id=intent.id, research_run_id=run.id)
        session.add(family)
        session.commit()
        session.refresh(family)
        variant = PromptVariant(prompt_family_id=family.id, text="أي مطحنة قهوة تنصحني فيها؟")
        session.add(variant)
        session.commit()
        session.refresh(variant)
        session.add(
            AIVisibilityObservation(
                store_id=store.id,
                intent_id=intent.id,
                prompt_variant_id=variant.id,
                research_run_id=run.id,
                provider="openai",
                model="gpt-4o-mini",
                country="sa",
                language="ar",
                mentioned=False,
                # Part G-B5 — this is the signal that was previously mined
                # nowhere: a plain-text brand mention with no URL, which is
                # what a non-grounded chat completion actually returns.
                competitors_mentioned=["rival.co"],
            )
        )
        session.commit()

    return store, run


def _make_settings(**overrides) -> Settings:
    defaults = dict(
        research_max_search_requests=20,
        research_max_ai_requests=20,
        research_max_pages=20,
        research_max_tokens=100_000,
        research_max_cost_usd=5.0,
        research_max_duration_seconds=60.0,
        research_max_depth=3,
        research_max_tasks=10,
    )
    defaults.update(overrides)
    return Settings(**defaults)


async def test_loop_builds_task_tree_and_dedups_repeated_suggestion(session, monkeypatch):
    store, run = _seed_store_with_serp_observation(session)

    async def fake_safe_fetch(url, policy):
        return FetchResult(url=url, status_code=200, content_type="text/html", text=COMPETITOR_HTML)

    monkeypatch.setattr(gap_engine_module, "safe_fetch", fake_safe_fetch)
    monkeypatch.setattr(loop_module, "PLANNER_INTERVAL", 1)

    router = ModelRouter(
        providers={"planner": FakePlannerProvider(), "gap": FakeGapProvider()},
        routes={
            "research_planning": TaskRoute(primary=ModelChoice("planner", "fake-model")),
            "page_gap_analysis": TaskRoute(primary=ModelChoice("gap", "fake-model")),
        },
    )

    metrics = await run_iterative_research_loop(
        session=session,
        router=router,
        storage=_FakeStorage(),
        search_provider=NullSearchProvider(),
        settings=_make_settings(),
        store=store,
        run=run,
        agent_run_id=None,
    )

    tasks = session.exec(select(ResearchTask).where(ResearchTask.research_run_id == run.id)).all()
    by_type_status = {(t.task_type, t.status) for t in tasks}

    seed = next(t for t in tasks if t.task_type == TaskType.competitor_discovery_batch)
    deep_dive = next(t for t in tasks if t.task_type == TaskType.competitor_deep_dive and t.status == TaskStatus.completed)
    duplicate = next(t for t in tasks if t.status == TaskStatus.skipped_duplicate)

    assert seed.parent_task_id is None
    assert seed.depth == 0
    assert deep_dive.parent_task_id == seed.id
    assert deep_dive.depth == 1
    assert duplicate.parent_task_id == deep_dive.id
    assert duplicate.depth == 2
    assert (TaskType.competitor_discovery_batch, TaskStatus.completed) in by_type_status

    assert metrics.total_tasks == len(tasks)
    assert metrics.research_depth_reached == 2
    assert metrics.competitor_pages_analyzed == 1

    competitors = session.exec(select(Competitor).where(Competitor.store_id == store.id)).all()
    assert len(competitors) == 1
    assert competitors[0].domain == "rival.co"


async def test_loop_calls_planner_before_queue_empties_even_below_planner_interval(session, monkeypatch):
    """Regression: with only the seed task ever queued, completed_since_planning
    never reaches the default PLANNER_INTERVAL (3) before the queue empties —
    interval-gating alone means the Planner is never consulted at all. The
    loop must also plan when the queue is about to run dry, regardless of
    the interval (this is what a real single-seed run looks like)."""
    store, run = _seed_store_with_serp_observation(session)
    # PLANNER_INTERVAL left at its real default (3) on purpose.

    router = ModelRouter(
        providers={"planner": FakePlannerProvider()},
        routes={"research_planning": TaskRoute(primary=ModelChoice("planner", "fake-model"))},
    )

    await run_iterative_research_loop(
        session=session,
        router=router,
        storage=_FakeStorage(),
        search_provider=NullSearchProvider(),
        settings=_make_settings(),
        store=store,
        run=run,
        agent_run_id=None,
    )

    tasks = session.exec(select(ResearchTask).where(ResearchTask.research_run_id == run.id)).all()
    # Seed (depth 0) + at least the proposed competitor_deep_dive child
    # (depth 1) — proof the Planner actually ran after just 1 completion.
    assert len(tasks) >= 2
    assert any(t.task_type == TaskType.competitor_deep_dive for t in tasks)


async def test_loop_records_dead_end_fields_on_completed_tasks(session, monkeypatch):
    """Part G-B4/G-B5: the seed task now mines ai_visibility_observations
    only (SERP-sourced competitors are seeded earlier in production, see
    _seed_store_with_serp_observation) — with a real 'rival.co' brand
    mention present, it produces a new ai_visibility CompetitorRelationship
    (useful=True, new_competitors_count=1). The follow-up competitor_deep_dive
    it triggers produces a page-gap finding's evidence (useful=True); the
    dominant_competitor finding rule itself needs more SERP appearances than
    this fixture has, so 0 findings there is the correct, honest answer."""
    store, run = _seed_store_with_serp_observation(session, with_ai_visibility_mention=True)

    async def fake_safe_fetch(url, policy):
        return FetchResult(url=url, status_code=200, content_type="text/html", text=COMPETITOR_HTML)

    monkeypatch.setattr(gap_engine_module, "safe_fetch", fake_safe_fetch)
    monkeypatch.setattr(loop_module, "PLANNER_INTERVAL", 1)

    router = ModelRouter(
        providers={"planner": FakePlannerProvider(), "gap": FakeGapProvider()},
        routes={
            "research_planning": TaskRoute(primary=ModelChoice("planner", "fake-model")),
            "page_gap_analysis": TaskRoute(primary=ModelChoice("gap", "fake-model")),
        },
    )

    await run_iterative_research_loop(
        session=session,
        router=router,
        storage=_FakeStorage(),
        search_provider=NullSearchProvider(),
        settings=_make_settings(),
        store=store,
        run=run,
        agent_run_id=None,
    )

    tasks = session.exec(select(ResearchTask).where(ResearchTask.research_run_id == run.id)).all()
    seed = next(t for t in tasks if t.task_type == TaskType.competitor_discovery_batch)
    deep_dive = next(t for t in tasks if t.task_type == TaskType.competitor_deep_dive and t.status == TaskStatus.completed)
    duplicate = next(t for t in tasks if t.status == TaskStatus.skipped_duplicate)

    assert seed.useful is True
    assert seed.new_competitors_count == 1
    assert deep_dive.useful is True
    assert deep_dive.new_evidence_count >= 1
    # A skipped_duplicate task never executes — its dead-end fields must
    # stay at their untouched defaults, not be silently marked useful/useless.
    assert duplicate.useful is None
    assert duplicate.new_findings_count == 0


async def test_loop_dampens_priority_for_task_type_with_poor_track_record(session, monkeypatch):
    """Part G-B4: query_expansion already has 2 completed dead-end samples
    in this run before the Planner proposes a third — its priority must be
    cut deterministically, regardless of what priority the Planner itself
    assigned."""
    store, run = _seed_store_with_serp_observation(session)
    intent = session.exec(select(Intent).where(Intent.research_run_id == run.id)).one()

    for i in range(2):
        session.add(
            ResearchTask(
                research_run_id=run.id,
                store_id=store.id,
                task_type=TaskType.query_expansion,
                status=TaskStatus.completed,
                priority=0.5,
                depth=1,
                fingerprint=f"preseeded-dead-end-{i}",
                useful=False,
            )
        )
    session.commit()

    monkeypatch.setattr(loop_module, "PLANNER_INTERVAL", 1)

    class QueryExpansionPlanner(AIProvider):
        name = "fake_planner_qe"

        async def generate(self, request: AIRequest) -> AIResponse:
            payload = json.dumps(
                {
                    "new_tasks": [
                        {
                            "task_type": "query_expansion",
                            "target": f"id={intent.id}",
                            "reason": "توسيع كلمات إضافية لهذه النية",
                            "hypothesis": None,
                            "priority": 0.8,
                        }
                    ]
                }
            )
            return AIResponse(
                provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=5, output_tokens=5)
            )

    router = ModelRouter(
        providers={"planner": QueryExpansionPlanner()},
        routes={"research_planning": TaskRoute(primary=ModelChoice("planner", "fake-model"))},
    )

    await run_iterative_research_loop(
        session=session,
        router=router,
        storage=_FakeStorage(),
        search_provider=NullSearchProvider(),
        settings=_make_settings(),
        store=store,
        run=run,
        agent_run_id=None,
    )

    newly_proposed = session.exec(
        select(ResearchTask)
        .where(ResearchTask.research_run_id == run.id)
        .where(ResearchTask.task_type == TaskType.query_expansion)
        .where(ResearchTask.fingerprint.not_in(["preseeded-dead-end-0", "preseeded-dead-end-1"]))  # type: ignore[union-attr]
    ).first()

    assert newly_proposed is not None
    assert newly_proposed.priority == 0.8 * 0.5


async def test_loop_rejects_planner_suggestion_for_unavailable_task_type(session, monkeypatch):
    """Defense-in-depth (Part G-B4): even if plan_next_tasks's own filter
    were bypassed, the loop's acceptance logic must independently refuse to
    enqueue a task type the current run's capabilities don't support."""
    store, run = _seed_store_with_serp_observation(session)
    monkeypatch.setattr(loop_module, "PLANNER_INTERVAL", 1)

    from app.research.capabilities import ResearchCapabilities
    from app.schemas.research_planning import NewTaskSuggestion

    async def fake_plan_next_tasks(**kwargs):
        return [
            NewTaskSuggestion(
                task_type=TaskType.ai_visibility_gemini,
                target=f"id={session.exec(select(Intent).where(Intent.research_run_id == run.id)).one().id}",
                reason="فحص Gemini",
                hypothesis=None,
                priority=0.9,
            )
        ]

    monkeypatch.setattr(loop_module, "plan_next_tasks", fake_plan_next_tasks)
    monkeypatch.setattr(
        loop_module,
        "resolve_research_capabilities",
        lambda router, settings: ResearchCapabilities(configured_ai_surfaces=frozenset(), search_configured=True),
    )

    router = ModelRouter(providers={}, routes={})

    await run_iterative_research_loop(
        session=session,
        router=router,
        storage=_FakeStorage(),
        search_provider=NullSearchProvider(),
        settings=_make_settings(),
        store=store,
        run=run,
        agent_run_id=None,
    )

    tasks = session.exec(select(ResearchTask).where(ResearchTask.research_run_id == run.id)).all()
    assert all(t.task_type != TaskType.ai_visibility_gemini for t in tasks)


async def test_loop_stops_when_task_budget_exhausted(session, monkeypatch):
    store, run = _seed_store_with_serp_observation(session)
    monkeypatch.setattr(loop_module, "PLANNER_INTERVAL", 1)

    router = ModelRouter(
        providers={"planner": FakePlannerProvider()},
        routes={"research_planning": TaskRoute(primary=ModelChoice("planner", "fake-model"))},
    )

    metrics = await run_iterative_research_loop(
        session=session,
        router=router,
        storage=_FakeStorage(),
        search_provider=NullSearchProvider(),
        settings=_make_settings(research_max_tasks=1),
        store=store,
        run=run,
        agent_run_id=None,
    )

    tasks = session.exec(select(ResearchTask).where(ResearchTask.research_run_id == run.id)).all()
    assert len(tasks) == 1
    assert tasks[0].task_type == TaskType.competitor_discovery_batch
    assert tasks[0].status == TaskStatus.completed
    assert metrics.total_tasks == 1


class ThreeCompetitorPlannerProvider(AIProvider):
    """Part H4 — proposes competitor_deep_dive for three independent
    competitors in one round (then nothing further), so the loop has real
    same-level, no-dependency-between-them tasks to batch-dispatch."""

    name = "three_planner"

    def __init__(self):
        self.call_count = 0

    async def generate(self, request: AIRequest) -> AIResponse:
        self.call_count += 1
        if self.call_count > 1:
            payload = json.dumps({"new_tasks": []})
        else:
            payload = json.dumps(
                {
                    "new_tasks": [
                        {
                            "task_type": "competitor_deep_dive", "target": domain,
                            "reason": "يظهر بقوة في هذه النية", "hypothesis": None, "priority": 0.9,
                        }
                        for domain in ("rival-a.co", "rival-b.co", "rival-c.co")
                    ]
                }
            )
        return AIResponse(
            provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=10, output_tokens=10)
        )


async def test_loop_dispatches_independent_tasks_in_a_concurrent_batch(session, monkeypatch):
    """Part H4 — the true end-to-end proof: three independent
    competitor_deep_dive tasks (no dependency between them) proposed in one
    planning round genuinely overlap in execution, not A -> wait -> B -> wait -> C."""
    store, run = _seed_store_with_serp_observation(session)

    # Seed two more competitors (rival.co already exists via the base
    # fixture's mine_serp_competitors call) sharing the same intent, so all
    # three domains have a real CompetitorRelationship(source=serp) for
    # resolve_task_input to resolve.
    from app.competitors.discovery_engine import get_or_create_competitor
    from app.models.competitor import CompetitorRelationship, CompetitorType, RelationshipSource

    intent = session.exec(select(Intent).where(Intent.research_run_id == run.id)).one()
    for domain in ("rival-a.co", "rival-b.co", "rival-c.co"):
        competitor = get_or_create_competitor(
            session, store_id=store.id, domain=domain, competitor_type=CompetitorType.search_competitor,
            research_run_id=run.id,
        )
        session.add(
            CompetitorRelationship(
                competitor_id=competitor.id, intent_id=intent.id, research_run_id=run.id,
                source=RelationshipSource.serp, rank_or_position=1,
            )
        )
    session.commit()
    serp_obs = session.exec(select(SerpObservation).where(SerpObservation.research_run_id == run.id)).one()
    serp_obs.results = serp_obs.results + [
        {"rank": 2, "domain": "rival-a.co", "url": "https://rival-a.co/x"},
        {"rank": 3, "domain": "rival-b.co", "url": "https://rival-b.co/x"},
        {"rank": 4, "domain": "rival-c.co", "url": "https://rival-c.co/x"},
    ]
    session.add(serp_obs)
    session.commit()

    in_flight = {"count": 0, "peak": 0}

    async def tracking_safe_fetch(url, policy):
        import asyncio

        in_flight["count"] += 1
        in_flight["peak"] = max(in_flight["peak"], in_flight["count"])
        await asyncio.sleep(0.05)
        in_flight["count"] -= 1
        return FetchResult(url=url, status_code=200, content_type="text/html", text=COMPETITOR_HTML)

    monkeypatch.setattr(gap_engine_module, "safe_fetch", tracking_safe_fetch)
    monkeypatch.setattr(loop_module, "PLANNER_INTERVAL", 1)

    router = ModelRouter(
        providers={"planner": ThreeCompetitorPlannerProvider(), "gap": FakeGapProvider()},
        routes={
            "research_planning": TaskRoute(primary=ModelChoice("planner", "fake-model")),
            "page_gap_analysis": TaskRoute(primary=ModelChoice("gap", "fake-model")),
        },
    )

    await run_iterative_research_loop(
        session=session,
        router=router,
        storage=_FakeStorage(),
        search_provider=NullSearchProvider(),
        settings=_make_settings(research_max_concurrency=3),
        store=store,
        run=run,
        agent_run_id=None,
    )

    deep_dives = session.exec(
        select(ResearchTask)
        .where(ResearchTask.research_run_id == run.id)
        .where(ResearchTask.task_type == TaskType.competitor_deep_dive)
        .where(ResearchTask.status == TaskStatus.completed)
    ).all()
    assert len(deep_dives) == 3
    # The real proof: at least two of the three genuinely overlapped in
    # execution — not strictly sequential.
    assert in_flight["peak"] >= 2


async def test_loop_stops_dispatching_once_cancellation_is_requested_mid_run(session, monkeypatch):
    """Part H8 — cancellation requested while a task is in flight lets that
    task finish (in-flight work is not torn down mid-write), but the loop
    must never dispatch (mark `running` and execute) another task
    afterward. Any task a planning round still proposes before the next
    stop-check may exist as a row, but must stay `pending` forever, never
    `running`/`completed`."""
    from app.research.cancellation import CANCELLATION_STOP_REASON, request_run_cancellation

    store, run = _seed_store_with_serp_observation(session)

    async def fake_safe_fetch(url, policy):
        return FetchResult(url=url, status_code=200, content_type="text/html", text=COMPETITOR_HTML)

    monkeypatch.setattr(gap_engine_module, "safe_fetch", fake_safe_fetch)
    monkeypatch.setattr(loop_module, "PLANNER_INTERVAL", 1)

    class CancellingGapProvider(AIProvider):
        name = "gap"

        async def generate(self, request: AIRequest) -> AIResponse:
            # Simulates an external actor (a different process/session)
            # requesting cancellation while this task is genuinely in
            # flight — the task itself still completes normally.
            request_run_cancellation(session, run.id)
            payload = json.dumps(
                {"gaps": ["دليل شراء غير موجود عندنا"], "recommendation_summary": "أضف دليل شراء.", "confidence": 0.7}
            )
            return AIResponse(
                provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=10, output_tokens=10)
            )

    router = ModelRouter(
        providers={"planner": FakePlannerProvider(), "gap": CancellingGapProvider()},
        routes={
            "research_planning": TaskRoute(primary=ModelChoice("planner", "fake-model")),
            "page_gap_analysis": TaskRoute(primary=ModelChoice("gap", "fake-model")),
        },
    )

    metrics = await run_iterative_research_loop(
        session=session,
        router=router,
        storage=_FakeStorage(),
        search_provider=NullSearchProvider(),
        settings=_make_settings(),
        store=store,
        run=run,
        agent_run_id=None,
    )

    assert metrics.stop_reason == CANCELLATION_STOP_REASON

    tasks = session.exec(select(ResearchTask).where(ResearchTask.research_run_id == run.id)).all()
    # Seed and the one deep_dive that was genuinely in flight when
    # cancellation fired both got to finish.
    completed = [t for t in tasks if t.status == TaskStatus.completed]
    assert {t.task_type for t in completed} == {TaskType.competitor_discovery_batch, TaskType.competitor_deep_dive}
    # Nothing dispatched after the cancellation request — any further
    # planner proposal stays pending forever, never running/completed.
    assert all(t.status in (TaskStatus.pending, TaskStatus.completed, TaskStatus.skipped_duplicate) for t in tasks)
    assert not any(t.status == TaskStatus.running for t in tasks)
