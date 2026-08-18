import json
import uuid

from sqlmodel import select

from app.core.config import Settings
from app.core.evaluation_mode import EvaluationMode
from app.crawler.fetch import FetchResult
from app.crawler.security import CrawlSecurityPolicy
from app.intent.intent_engine import _attach_keywords
from app.models.ai_visibility import AIVisibilityObservation, PromptFamily, PromptVariant
from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.finding import Finding, FindingStatus
from app.models.intent import Intent, IntentSource
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.research_task import ResearchTask, TaskStatus, TaskType
from app.models.serp import SerpObservation
from app.models.store import Store
from app.page_intelligence import gap_engine as gap_engine_module
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute
from app.providers.search.base import SearchProvider, SearchRequest, SearchResponse, SearchResultItem
from app.research.executor import (
    TaskContext,
    execute_ai_visibility_chatgpt,
    execute_competitor_deep_dive,
    execute_competitor_discovery_batch,
    execute_query_expansion,
    execute_search_google,
    execute_validate_cross_surface_finding,
    execute_validate_finding,
)

COMPETITOR_HTML = (
    "<html><head><title>Grinder Guide</title></head><body><h1>Grinder Guide</h1></body></html>"
)


class FakeIntentExpansionProvider(AIProvider):
    name = "fake_intent_expansion"

    async def generate(self, request: AIRequest) -> AIResponse:
        payload = json.dumps(
            {
                "intents": [
                    {
                        "topic": "افضل مطحنة قهوة يدوية",
                        "category": "أدوات القهوة",
                        "commercial_stage": "consideration",
                        "estimated_demand": "medium",
                        "keywords": ["مطحنة قهوة يدوية"],
                        "confidence": 0.7,
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
            {
                "gaps": ["دليل شامل غير موجود عندنا"],
                "recommendation_summary": "أضف دليلًا شاملًا.",
                "confidence": 0.7,
            }
        )
        return AIResponse(
            provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=10, output_tokens=10)
        )


class FakeSearchProviderFixedResult(SearchProvider):
    name = "fake_search"

    def __init__(self, results):
        self._results = results

    async def search(self, request: SearchRequest) -> SearchResponse:
        return SearchResponse(provider=self.name, results=self._results, latency_ms=1)


def _base_scenario(session):
    org = Organization(name="t", slug="t-executor")
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
    return org, store, run


def _make_task(store, run, task_type, input_=None, **overrides):
    return ResearchTask(
        research_run_id=run.id,
        store_id=store.id,
        task_type=task_type,
        status=TaskStatus.running,
        fingerprint=f"fp-{uuid.uuid4()}",
        input=input_ or {},
        **overrides,
    )


async def test_execute_competitor_discovery_batch_mines_ai_visibility_mentions(session):
    """Part G-B5: the seed task now mines only ai_visibility_observations —
    SERP-sourced competitors are seeded earlier in the fixed pipeline (see
    app.competitors.discovery_engine.mine_serp_competitors, called from
    ResearchOrchestrator right after serp_agent_run), not by this task."""
    org, store, run = _base_scenario(session)
    intent = Intent(
        store_id=store.id,
        research_run_id=run.id,
        topic="topic",
        country="sa",
        language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    family = PromptFamily(intent_id=intent.id, research_run_id=run.id)
    session.add(family)
    session.commit()
    session.refresh(family)
    variant = PromptVariant(prompt_family_id=family.id, text="question")
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
            # No citation URL — this is what a real, non-grounded chat
            # completion returns; the brand-name text match is the only
            # realistic signal (Part G-B5).
            competitors_mentioned=["rival.co"],
        )
    )
    session.commit()

    ctx = TaskContext(
        session=session,
        router=None,
        storage=None,
        search_provider=None,
        settings=None,
        store=store,
        run=run,
        agent_run_id=None,
    )
    task = _make_task(store, run, TaskType.competitor_discovery_batch)

    result = await execute_competitor_discovery_batch(ctx, task)

    assert result.discovered_entities["unique_competitors"] == 1
    assert "منافس" in result.result_summary
    competitors = session.exec(select(Competitor).where(Competitor.store_id == store.id)).all()
    assert len(competitors) == 1
    assert competitors[0].domain == "rival.co"
    assert competitors[0].competitor_type == CompetitorType.ai_recommendation_competitor


async def test_execute_competitor_deep_dive_produces_gap_analysis(session, monkeypatch):
    org, store, run = _base_scenario(session)
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
    from app.models.intent import Keyword

    keyword = session.exec(select(Keyword)).one()

    competitor = Competitor(
        store_id=store.id,
        domain="rival.test",
        name="rival.test",
        competitor_type=CompetitorType.search_competitor,
        first_seen_research_run_id=run.id,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)

    session.add(
        SerpObservation(
            store_id=store.id,
            intent_id=intent.id,
            keyword_id=keyword.id,
            research_run_id=run.id,
            country="sa",
            language="ar",
            results=[{"rank": 1, "domain": "rival.test", "url": "https://rival.test/grinders"}],
            client_rank=None,
        )
    )
    session.commit()

    async def fake_safe_fetch(url, policy):
        return FetchResult(url=url, status_code=200, content_type="text/html", text=COMPETITOR_HTML)

    monkeypatch.setattr(gap_engine_module, "safe_fetch", fake_safe_fetch)

    router = ModelRouter(
        providers={"fake": FakeGapProvider()},
        routes={"page_gap_analysis": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )
    settings = type(
        "S",
        (),
        {"crawler_max_response_bytes": 1_000_000, "crawler_request_timeout_seconds": 5, "crawler_user_agent": "TestBot/1.0"},
    )()

    ctx = TaskContext(
        session=session, router=router, storage=_FakeStorage(), search_provider=None,
        settings=settings, store=store, run=run, agent_run_id=None,
    )
    task = _make_task(
        store, run, TaskType.competitor_deep_dive,
        input_={"competitor_id": str(competitor.id), "intent_id": str(intent.id)},
    )

    result = await execute_competitor_deep_dive(ctx, task)

    assert result.discovered_entities["gaps_found"] == 1
    assert len(result.evidence_ids) == 1
    evidence = session.exec(select(Evidence).where(Evidence.source_type == EvidenceSourceType.page_gap_analysis)).all()
    assert len(evidence) == 1


class _FakeStorage:
    def put_text(self, key_prefix, content, content_type="text/html"):
        return f"s3://fake/{key_prefix}/key"


async def test_execute_competitor_deep_dive_missing_input_is_handled_gracefully(session):
    org, store, run = _base_scenario(session)
    ctx = TaskContext(
        session=session, router=None, storage=None, search_provider=None,
        settings=None, store=store, run=run, agent_run_id=None,
    )
    task = _make_task(store, run, TaskType.competitor_deep_dive, input_={})

    result = await execute_competitor_deep_dive(ctx, task)

    assert "ناقصة" in result.result_summary
    assert result.evidence_ids == []


async def test_execute_query_expansion_generates_variants_for_one_intent(session):
    org, store, run = _base_scenario(session)
    intent = Intent(
        store_id=store.id,
        research_run_id=run.id,
        topic="مطحنة قهوة",
        country="sa",
        language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    router = ModelRouter(
        providers={"fake": FakeIntentExpansionProvider()},
        routes={"intent_expansion": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )
    ctx = TaskContext(
        session=session, router=router, storage=None, search_provider=None,
        settings=None, store=store, run=run, agent_run_id=None,
    )
    task = _make_task(store, run, TaskType.query_expansion, input_={"intent_id": str(intent.id)})

    result = await execute_query_expansion(ctx, task)

    assert result.discovered_entities["intents_generated"] == 1
    new_intents = session.exec(select(Intent).where(Intent.source == IntentSource.ai_expansion)).all()
    assert len(new_intents) == 1
    assert new_intents[0].topic == "افضل مطحنة قهوة يدوية"


async def test_execute_validate_finding_with_intent_boosts_confidence_when_competitor_still_appears(session):
    org, store, run = _base_scenario(session)
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

    competitor = Competitor(
        store_id=store.id,
        domain="rival.test",
        name="rival.test",
        competitor_type=CompetitorType.search_competitor,
        first_seen_research_run_id=run.id,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)

    finding = Finding(
        store_id=store.id,
        research_run_id=run.id,
        finding_type="dominant_competitor",
        statement="rival.test يهيمن",
        confidence=0.5,
        affected_competitors=[str(competitor.id)],
        affected_intents=[str(intent.id)],
        status=FindingStatus.candidate,
    )
    session.add(finding)
    session.commit()
    session.refresh(finding)

    search_provider = FakeSearchProviderFixedResult(
        [SearchResultItem(rank=1, domain="rival.test", url="https://rival.test/x")]
    )
    settings = type("S", (), {"serp_num_results": 10})()
    ctx = TaskContext(
        session=session, router=None, storage=None, search_provider=search_provider,
        settings=settings, store=store, run=run, agent_run_id=None,
    )
    task = _make_task(store, run, TaskType.validate_finding, input_={"finding_id": str(finding.id)})

    result = await execute_validate_finding(ctx, task)

    session.refresh(finding)
    assert finding.confidence == 0.65
    assert finding.validation_count == 1
    assert "google" in result.result_summary
    assert finding.evidence_breakdown["google"]["checked"] is True

    # The extra SERP check must be tagged Discovery-tier, not mixed into Control.
    origin_tagged = session.exec(select(SerpObservation).where(SerpObservation.origin_task_id == task.id)).all()
    assert len(origin_tagged) == 1


async def test_execute_validate_finding_without_intent_uses_deterministic_recheck(session):
    org, store, run = _base_scenario(session)
    competitor = Competitor(
        store_id=store.id,
        domain="rival.test",
        name="rival.test",
        competitor_type=CompetitorType.search_competitor,
        first_seen_research_run_id=run.id,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)

    intent = Intent(
        store_id=store.id, research_run_id=run.id, topic="t", country="sa", language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    for _ in range(3):
        session.add(
            CompetitorRelationship(
                competitor_id=competitor.id, intent_id=intent.id, research_run_id=run.id,
                source=RelationshipSource.serp, rank_or_position=1,
            )
        )
    session.commit()

    finding = Finding(
        store_id=store.id, research_run_id=run.id, finding_type="dominant_competitor",
        statement="rival.test يهيمن", confidence=0.5,
        affected_competitors=[str(competitor.id)], affected_intents=[], status=FindingStatus.candidate,
    )
    session.add(finding)
    session.commit()
    session.refresh(finding)

    ctx = TaskContext(
        session=session, router=None, storage=None, search_provider=None,
        settings=None, store=store, run=run, agent_run_id=None,
    )
    task = _make_task(store, run, TaskType.validate_finding, input_={"finding_id": str(finding.id)})

    result = await execute_validate_finding(ctx, task)

    session.refresh(finding)
    assert finding.confidence == 0.65
    assert "store" in result.result_summary
    assert finding.evidence_breakdown["store"]["checked"] is True


async def test_execute_search_google_tags_origin_task_id(session):
    org, store, run = _base_scenario(session)
    intent = Intent(
        store_id=store.id, research_run_id=run.id, topic="coffee grinder", country="sa", language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    _attach_keywords(session, intent, ["coffee grinder"], "sa", "ar")

    search_provider = FakeSearchProviderFixedResult(
        [SearchResultItem(rank=1, domain="store.example", url="https://store.example/x")]
    )
    settings = type("S", (), {"serp_num_results": 10})()
    ctx = TaskContext(
        session=session, router=None, storage=None, search_provider=search_provider,
        settings=settings, store=store, run=run, agent_run_id=None,
    )
    task = _make_task(store, run, TaskType.search_google, input_={"intent_id": str(intent.id)})

    result = await execute_search_google(ctx, task)

    assert "رتبة 1" in result.result_summary
    origin_tagged = session.exec(select(SerpObservation).where(SerpObservation.origin_task_id == task.id)).all()
    assert len(origin_tagged) == 1


async def test_execute_search_google_is_idempotent_on_redispatch(session):
    """Part H7 — if the same task is somehow re-dispatched (e.g. a crash
    between commit and ack), re-running it must not issue a second real
    query or create a second SerpObservation."""
    org, store, run = _base_scenario(session)
    intent = Intent(
        store_id=store.id, research_run_id=run.id, topic="coffee grinder", country="sa", language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    _attach_keywords(session, intent, ["coffee grinder"], "sa", "ar")

    call_count = {"n": 0}

    class CountingSearchProvider(SearchProvider):
        name = "counting_search"

        async def search(self, request: SearchRequest) -> SearchResponse:
            call_count["n"] += 1
            return SearchResponse(
                provider=self.name,
                results=[SearchResultItem(rank=1, domain="store.example", url="https://store.example/x")],
                latency_ms=1,
            )

    settings = type("S", (), {"serp_num_results": 10})()
    ctx = TaskContext(
        session=session, router=None, storage=None, search_provider=CountingSearchProvider(),
        settings=settings, store=store, run=run, agent_run_id=None,
    )
    task = _make_task(store, run, TaskType.search_google, input_={"intent_id": str(intent.id)})

    first = await execute_search_google(ctx, task)
    second = await execute_search_google(ctx, task)

    assert call_count["n"] == 1  # the second call never touched the real provider
    assert "مكرر" in second.result_summary
    assert first.discovered_entities["serp_observations"] == 1
    assert second.discovered_entities["serp_observations"] == 0
    origin_tagged = session.exec(select(SerpObservation).where(SerpObservation.origin_task_id == task.id)).all()
    assert len(origin_tagged) == 1


class FakeChatGPTProvider(AIProvider):
    name = "openai"

    async def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            provider=self.name, model=request.model, text="أنصحك بمتجر Example Store لهذا المنتج.",
            usage=AIUsage(input_tokens=5, output_tokens=5),
        )


async def test_execute_ai_visibility_chatgpt_probes_existing_prompt_variant(session):
    org, store, run = _base_scenario(session)
    intent = Intent(
        store_id=store.id, research_run_id=run.id, topic="coffee grinder", country="sa", language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    family = PromptFamily(intent_id=intent.id, research_run_id=run.id)
    session.add(family)
    session.commit()
    session.refresh(family)
    variant = PromptVariant(prompt_family_id=family.id, text="وش أفضل محمصة قهوة؟")
    session.add(variant)
    session.commit()
    session.refresh(variant)

    router = ModelRouter(providers={"openai": FakeChatGPTProvider()})
    ctx = TaskContext(
        session=session, router=router, storage=None, search_provider=None,
        settings=Settings(evaluation_mode=EvaluationMode.live), store=store, run=run, agent_run_id=None,
    )
    task = _make_task(store, run, TaskType.ai_visibility_chatgpt, input_={"intent_id": str(intent.id)})

    result = await execute_ai_visibility_chatgpt(ctx, task)

    assert result.discovered_entities["ai_visibility_observations"] == 1
    observations = session.exec(select(AIVisibilityObservation).where(AIVisibilityObservation.origin_task_id == task.id)).all()
    assert len(observations) == 1
    assert observations[0].surface == "chatgpt"


async def test_execute_ai_visibility_chatgpt_is_idempotent_on_redispatch(session):
    """Part H7 — same guarantee as execute_search_google: re-running the
    same task must never issue a second real probe or duplicate the
    observation."""
    org, store, run = _base_scenario(session)
    intent = Intent(
        store_id=store.id, research_run_id=run.id, topic="coffee grinder", country="sa", language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    family = PromptFamily(intent_id=intent.id, research_run_id=run.id)
    session.add(family)
    session.commit()
    session.refresh(family)
    variant = PromptVariant(prompt_family_id=family.id, text="وش أفضل محمصة قهوة؟")
    session.add(variant)
    session.commit()
    session.refresh(variant)

    call_count = {"n": 0}

    class CountingChatGPTProvider(AIProvider):
        name = "openai"

        async def generate(self, request: AIRequest) -> AIResponse:
            call_count["n"] += 1
            return AIResponse(
                provider=self.name, model=request.model, text="أنصحك بمتجر Example Store لهذا المنتج.",
                usage=AIUsage(input_tokens=5, output_tokens=5),
            )

    router = ModelRouter(providers={"openai": CountingChatGPTProvider()})
    ctx = TaskContext(
        session=session, router=router, storage=None, search_provider=None,
        settings=Settings(evaluation_mode=EvaluationMode.live), store=store, run=run, agent_run_id=None,
    )
    task = _make_task(store, run, TaskType.ai_visibility_chatgpt, input_={"intent_id": str(intent.id)})

    first = await execute_ai_visibility_chatgpt(ctx, task)
    second = await execute_ai_visibility_chatgpt(ctx, task)

    assert call_count["n"] == 1  # the second call never touched the real provider
    assert "مكرر" in second.result_summary
    assert first.discovered_entities["ai_visibility_observations"] == 1
    assert second.discovered_entities["ai_visibility_observations"] == 0
    observations = session.exec(
        select(AIVisibilityObservation).where(AIVisibilityObservation.origin_task_id == task.id)
    ).all()
    assert len(observations) == 1


async def test_execute_ai_visibility_chatgpt_skips_when_provider_not_configured(session):
    org, store, run = _base_scenario(session)
    intent = Intent(
        store_id=store.id, research_run_id=run.id, topic="coffee grinder", country="sa", language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    router = ModelRouter(providers={})
    ctx = TaskContext(
        session=session, router=router, storage=None, search_provider=None,
        settings=Settings(evaluation_mode=EvaluationMode.live), store=store, run=run, agent_run_id=None,
    )
    task = _make_task(store, run, TaskType.ai_visibility_chatgpt, input_={"intent_id": str(intent.id)})

    result = await execute_ai_visibility_chatgpt(ctx, task)

    assert "غير مُفعَّل" in result.result_summary
    assert session.exec(select(AIVisibilityObservation)).all() == []


async def test_execute_validate_cross_surface_finding_boosts_confidence_on_ai_mention(session):
    org, store, run = _base_scenario(session)
    competitor = Competitor(
        store_id=store.id, domain="rival.test", name="rival.test",
        competitor_type=CompetitorType.ai_recommendation_competitor, first_seen_research_run_id=run.id,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)

    finding = Finding(
        store_id=store.id, research_run_id=run.id, finding_type="dominant_competitor",
        statement="rival.test يهيمن على Google", confidence=0.5,
        affected_competitors=[str(competitor.id)], affected_intents=[], status=FindingStatus.candidate,
    )
    session.add(finding)
    session.commit()
    session.refresh(finding)

    session.add(
        AIVisibilityObservation(
            store_id=store.id, intent_id=uuid.uuid4(), prompt_variant_id=uuid.uuid4(), research_run_id=run.id,
            surface="chatgpt", provider="openai", model="gpt-4o-mini", country="sa", language="ar",
            mentioned=False, competitors_mentioned=["rival.test"],
        )
    )
    session.commit()

    ctx = TaskContext(
        session=session, router=None, storage=None, search_provider=None,
        settings=None, store=store, run=run, agent_run_id=None,
    )
    task = _make_task(store, run, TaskType.validate_cross_surface_finding, input_={"finding_id": str(finding.id)})

    result = await execute_validate_cross_surface_finding(ctx, task)

    session.refresh(finding)
    assert finding.confidence == 0.65
    assert result.discovered_entities["cross_surface_mentions"] == 1
