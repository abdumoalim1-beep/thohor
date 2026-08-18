import asyncio

from sqlmodel import select

from app.ai_visibility.surfaces import AISurface
from app.ai_visibility.visibility_engine import detect_mention, extract_links, run_ai_visibility_agent
from app.core.evaluation_mode import EvaluationMode
from app.crawler.store_intelligence import _upsert_brand
from app.models.ai_visibility import AIVisibilityObservation, PromptFamily, PromptVariant
from app.models.evidence import Evidence
from app.models.intent import Intent, IntentSource
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.stable_intent import StableIntent
from app.models.store import Store
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelRouter


class MentionsBrandProvider(AIProvider):
    name = "mentions"

    async def generate(self, request: AIRequest) -> AIResponse:
        text = "أنصحك بمتجر Roasting House، رابطه https://roastinghouse.sa/best-coffee — منتجاتهم ممتازة."
        return AIResponse(provider=self.name, model=request.model, text=text, usage=AIUsage(input_tokens=8, output_tokens=8))


class SilentProvider(AIProvider):
    name = "silent"

    async def generate(self, request: AIRequest) -> AIResponse:
        text = "جرب متجر آخر مثل Blue Bottle أو Starbucks."
        return AIResponse(provider=self.name, model=request.model, text=text, usage=AIUsage(input_tokens=8, output_tokens=8))


def test_detect_mention_finds_brand_name_case_insensitive():
    from app.models.catalog import Brand

    brand = Brand(store_id=None, name="Roasting House", aliases=["روستنج هاوس"])
    mentioned, position = detect_mention("we recommend roasting house for great coffee", brand)
    assert mentioned is True
    assert position == 13


def test_detect_mention_checks_aliases_too():
    from app.models.catalog import Brand

    brand = Brand(store_id=None, name="Roasting House", aliases=["روستنج هاوس"])
    mentioned, _ = detect_mention("جرب متجر روستنج هاوس فهو ممتاز", brand)
    assert mentioned is True


def test_detect_mention_false_when_no_match():
    from app.models.catalog import Brand

    brand = Brand(store_id=None, name="Roasting House", aliases=[])
    mentioned, position = detect_mention("try Blue Bottle instead", brand)
    assert mentioned is False
    assert position is None


def test_detect_mention_false_without_brand():
    mentioned, position = detect_mention("anything", None)
    assert mentioned is False
    assert position is None


def test_extract_links_finds_client_domain_only():
    text = "زوروا https://roastinghouse.sa/best-coffee أو https://competitor.example/x للمقارنة"
    citations, linked_domains, cited_domains = extract_links(text, "roastinghouse.sa")
    assert len(citations) == 2
    assert linked_domains == ["roastinghouse.sa"]
    assert cited_domains == ["competitor.example", "roastinghouse.sa"]


def _make_store_with_variant(session):
    org = Organization(name="t", slug="t-visibility")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://roastinghouse.sa")
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)

    _upsert_brand(session, store.id, "Roasting House", store.url)

    intent = Intent(
        store_id=store.id,
        research_run_id=run.id,
        topic="قهوة مختصة",
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

    variant = PromptVariant(prompt_family_id=family.id, text="وش أفضل محمصة قهوة؟")
    session.add(variant)
    session.commit()
    session.refresh(variant)

    return store, run, variant


async def test_run_ai_visibility_agent_detects_mention_and_creates_evidence(session):
    store, run, variant = _make_store_with_variant(session)
    router = ModelRouter(providers={"mentions": MentionsBrandProvider()})

    observations = await run_ai_visibility_agent(
        session=session,
        router=router,
        store_id=store.id,
        store_url=store.url,
        research_run_id=run.id,
        agent_run_id=None,
        prompt_variants=[variant],
        surfaces=[AISurface(surface="mentions-surface", provider="mentions", model="fake-model")],
        country="sa",
        language="ar",
        repetitions=2,
    )

    assert len(observations) == 2  # 1 variant x 1 engine x 2 repetitions
    assert all(o.mentioned for o in observations)
    assert all(o.linked_domains == ["roastinghouse.sa"] for o in observations)

    persisted = session.exec(select(AIVisibilityObservation)).all()
    assert len(persisted) == 2

    evidence = session.exec(select(Evidence)).all()
    assert len(evidence) == 2


async def test_run_ai_visibility_agent_records_non_mention(session):
    store, run, variant = _make_store_with_variant(session)
    router = ModelRouter(providers={"silent": SilentProvider()})

    observations = await run_ai_visibility_agent(
        session=session,
        router=router,
        store_id=store.id,
        store_url=store.url,
        research_run_id=run.id,
        agent_run_id=None,
        prompt_variants=[variant],
        surfaces=[AISurface(surface="silent-surface", provider="silent", model="fake-model")],
        country="sa",
        language="ar",
        repetitions=1,
    )

    assert len(observations) == 1
    assert observations[0].mentioned is False


def _make_store_with_stable_intent_variant(session):
    """Same shape as _make_store_with_variant, but with a real StableIntent
    linkage — needed for replay matching, which keys on stable_intent_id
    (the only identity that survives across research_runs)."""
    org = Organization(name="t", slug="t-visibility-replay")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://roastinghouse.sa")
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)

    stable_intent = StableIntent(
        store_id=store.id, canonical_topic="قهوة مختصة", normalized_topic="قهوة مختصة",
        country="sa", language="ar", locale="sa_ar",
    )
    session.add(stable_intent)
    session.commit()
    session.refresh(stable_intent)

    intent = Intent(
        store_id=store.id, research_run_id=run.id, topic="قهوة مختصة", country="sa", language="ar",
        source=IntentSource.deterministic_catalog, stable_intent_id=stable_intent.id,
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

    return store, run, variant, stable_intent, intent


async def test_run_ai_visibility_agent_replay_reuses_real_historical_observation(session):
    store, run, variant, stable_intent, intent = _make_store_with_stable_intent_variant(session)
    surface = AISurface(surface="chatgpt", provider="openai", model="gpt-4o-mini")

    historical = AIVisibilityObservation(
        store_id=store.id, intent_id=intent.id, stable_intent_id=stable_intent.id, prompt_variant_id=variant.id,
        research_run_id=run.id, provider="openai", model="gpt-4o-mini", surface="chatgpt",
        country="sa", language="ar", mentioned=True, mention_position=12,
        competitors_mentioned=["rival.test"], citations=[], linked_domains=["roastinghouse.sa"],
    )
    session.add(historical)
    session.commit()
    session.refresh(historical)

    # Empty providers dict — if the replay path ever actually called the
    # router, this would raise RuntimeError ("provider not configured"),
    # proving zero real calls happen in replay mode.
    router = ModelRouter(providers={})

    observations = await run_ai_visibility_agent(
        session=session, router=router, store_id=store.id, store_url=store.url,
        research_run_id=run.id, agent_run_id=None, prompt_variants=[variant], surfaces=[surface],
        country="sa", language="ar", repetitions=1, evaluation_mode=EvaluationMode.replay,
    )

    assert len(observations) == 1
    replayed = observations[0]
    assert replayed.id != historical.id
    assert replayed.replayed_from_observation_id == historical.id
    assert replayed.mentioned is True
    assert replayed.mention_position == 12
    assert replayed.competitors_mentioned == ["rival.test"]
    assert replayed.ai_execution_id is None

    evidence = session.exec(select(Evidence)).all()
    assert len(evidence) == 1
    assert "[replay]" in evidence[0].summary


async def test_run_ai_visibility_agent_replay_skips_when_no_historical_match(session):
    store, run, variant, stable_intent, intent = _make_store_with_stable_intent_variant(session)
    surface = AISurface(surface="chatgpt", provider="openai", model="gpt-4o-mini")
    router = ModelRouter(providers={})

    observations = await run_ai_visibility_agent(
        session=session, router=router, store_id=store.id, store_url=store.url,
        research_run_id=run.id, agent_run_id=None, prompt_variants=[variant], surfaces=[surface],
        country="sa", language="ar", repetitions=1, evaluation_mode=EvaluationMode.replay,
    )

    assert observations == []
    assert session.exec(select(AIVisibilityObservation)).all() == []


async def test_run_ai_visibility_agent_replay_uses_a_different_real_sample_per_repetition(session):
    store, run, variant, stable_intent, intent = _make_store_with_stable_intent_variant(session)
    surface = AISurface(surface="chatgpt", provider="openai", model="gpt-4o-mini")

    older = AIVisibilityObservation(
        store_id=store.id, intent_id=intent.id, stable_intent_id=stable_intent.id, prompt_variant_id=variant.id,
        research_run_id=run.id, provider="openai", model="gpt-4o-mini", surface="chatgpt",
        country="sa", language="ar", mentioned=False,
    )
    session.add(older)
    session.commit()
    newer = AIVisibilityObservation(
        store_id=store.id, intent_id=intent.id, stable_intent_id=stable_intent.id, prompt_variant_id=variant.id,
        research_run_id=run.id, provider="openai", model="gpt-4o-mini", surface="chatgpt",
        country="sa", language="ar", mentioned=True,
    )
    session.add(newer)
    session.commit()

    router = ModelRouter(providers={})
    observations = await run_ai_visibility_agent(
        session=session, router=router, store_id=store.id, store_url=store.url,
        research_run_id=run.id, agent_run_id=None, prompt_variants=[variant], surfaces=[surface],
        country="sa", language="ar", repetitions=2, evaluation_mode=EvaluationMode.replay,
    )

    assert len(observations) == 2
    replayed_source_ids = {o.replayed_from_observation_id for o in observations}
    assert replayed_source_ids == {older.id, newer.id}


class ConcurrencyTrackingProvider(AIProvider):
    """Part H5 — tracks peak simultaneous in-flight calls, proving live
    probes genuinely overlap instead of running one at a time."""

    name = "tracking"

    def __init__(self):
        self.in_flight = 0
        self.peak_in_flight = 0

    async def generate(self, request: AIRequest) -> AIResponse:
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        await asyncio.sleep(0.05)
        self.in_flight -= 1
        return AIResponse(provider=self.name, model=request.model, text="لا ذكر هنا", usage=AIUsage(input_tokens=5, output_tokens=5))


async def test_run_ai_visibility_agent_runs_live_probes_concurrently(session):
    store, run, variant = _make_store_with_variant(session)
    provider = ConcurrencyTrackingProvider()
    router = ModelRouter(providers={"tracking": provider})

    observations = await run_ai_visibility_agent(
        session=session, router=router, store_id=store.id, store_url=store.url,
        research_run_id=run.id, agent_run_id=None, prompt_variants=[variant],
        surfaces=[AISurface(surface="tracking-surface", provider="tracking", model="fake-model")],
        country="sa", language="ar", repetitions=4, max_concurrency=4,
    )

    assert len(observations) == 4
    assert provider.peak_in_flight == 4


async def test_run_ai_visibility_agent_respects_max_concurrency_ceiling(session):
    store, run, variant = _make_store_with_variant(session)
    provider = ConcurrencyTrackingProvider()
    router = ModelRouter(providers={"tracking": provider})

    await run_ai_visibility_agent(
        session=session, router=router, store_id=store.id, store_url=store.url,
        research_run_id=run.id, agent_run_id=None, prompt_variants=[variant],
        surfaces=[AISurface(surface="tracking-surface", provider="tracking", model="fake-model")],
        country="sa", language="ar", repetitions=6, max_concurrency=2,
    )

    assert provider.peak_in_flight == 2
