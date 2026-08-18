from sqlmodel import select

from app.ai_visibility.surfaces import AISurface
from app.core.evaluation_mode import EvaluationMode
from app.intent.intent_engine import _attach_keywords, get_or_create_stable_intent
from app.measurement.baseline import capture_measurement_baseline
from app.measurement.control_set import remeasure_control_set
from app.models.ai_visibility import AIVisibilityObservation, PromptFamily, PromptVariant
from app.models.intent import Intent, IntentSource, Keyword
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
from app.models.store import Store
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelRouter
from app.providers.search.base import SearchProvider, SearchRequest, SearchResponse, SearchResultItem


class FakeSearchProvider(SearchProvider):
    name = "fake-search"

    async def search(self, request: SearchRequest) -> SearchResponse:
        return SearchResponse(
            provider=self.name,
            results=[SearchResultItem(rank=1, domain="store.example", url="https://store.example/p")],
        )


class FakeAIProvider(AIProvider):
    name = "fake-ai"

    async def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            provider=self.name, model=request.model, text="نوصي بمتجر Store Example لهذا المنتج.",
            usage=AIUsage(input_tokens=5, output_tokens=5),
        )


async def _make_store_recommendation_with_baseline(session):
    org = Organization(name="t", slug="t-control-set")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)

    run_a = ResearchRun(store_id=store.id)
    session.add(run_a)
    session.commit()
    session.refresh(run_a)

    stable_intent = get_or_create_stable_intent(session, store_id=store.id, topic="grinder", country="sa", language="ar")
    intent = Intent(
        store_id=store.id, research_run_id=run_a.id, stable_intent_id=stable_intent.id, topic="grinder",
        country="sa", language="ar", source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    _attach_keywords(session, intent, ["grinder"], "sa", "ar")
    keyword = session.exec(select(Keyword).where(Keyword.text == "grinder")).one()

    session.add(
        SerpObservation(
            store_id=store.id, intent_id=intent.id, stable_intent_id=stable_intent.id, keyword_id=keyword.id,
            research_run_id=run_a.id, country="sa", language="ar", results=[], client_rank=None,
        )
    )
    session.commit()

    opportunity = Opportunity(
        store_id=store.id, research_run_id=run_a.id, opportunity_type="google_visibility_gap",
        title="t", description="d", status=OpportunityStatus.open, fingerprint="opp-fp-control-set",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    recommendation = Recommendation(
        store_id=store.id, opportunity_id=opportunity.id, first_seen_research_run_id=run_a.id,
        last_seen_research_run_id=run_a.id, title="t", what_to_do="do", why_it_matters="why",
        target_intents=[str(stable_intent.id)], status=RecommendationStatus.implemented,
        fingerprint="rec-fp-control-set",
    )
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)

    capture_measurement_baseline(session, recommendation, run_a.id)

    run_b = ResearchRun(store_id=store.id)
    session.add(run_b)
    session.commit()
    session.refresh(run_b)

    return store, recommendation, run_b, run_a, intent


async def test_remeasure_control_set_creates_fresh_serp_observation_for_target_stable_intent(session):
    store, recommendation, run_b, _run_a, _intent = await _make_store_recommendation_with_baseline(session)

    await remeasure_control_set(
        session=session, search_provider=FakeSearchProvider(), router=ModelRouter(providers={}), store=store,
        recommendation_id=recommendation.id, research_run_id=run_b.id, agent_run_id=None, ai_surfaces=[],
    )

    observations = session.exec(select(SerpObservation).where(SerpObservation.research_run_id == run_b.id)).all()
    assert len(observations) == 1
    assert observations[0].client_rank == 1  # our own domain came back top of the fake results
    assert str(observations[0].stable_intent_id) == recommendation.target_intents[0]


async def test_remeasure_control_set_is_idempotent_within_a_run(session):
    store, recommendation, run_b, _run_a, _intent = await _make_store_recommendation_with_baseline(session)

    for _ in range(2):
        await remeasure_control_set(
            session=session, search_provider=FakeSearchProvider(), router=ModelRouter(providers={}), store=store,
            recommendation_id=recommendation.id, research_run_id=run_b.id, agent_run_id=None, ai_surfaces=[],
        )

    observations = session.exec(select(SerpObservation).where(SerpObservation.research_run_id == run_b.id)).all()
    assert len(observations) == 1  # second call is a no-op, not a duplicate query


async def test_remeasure_control_set_probes_ai_surfaces_when_prompts_exist(session):
    store, recommendation, run_b, _run_a, _intent = await _make_store_recommendation_with_baseline(session)

    surface = AISurface(surface="fake-surface", provider="fake-ai", model="fake-model")
    router = ModelRouter(providers={"fake-ai": FakeAIProvider()})

    await remeasure_control_set(
        session=session, search_provider=FakeSearchProvider(), router=router, store=store,
        recommendation_id=recommendation.id, research_run_id=run_b.id, agent_run_id=None, ai_surfaces=[surface],
    )

    # No PromptVariant existed at baseline time in this fixture (baseline
    # target_prompts is empty since no AI visibility ran for run_a) — the
    # AI leg of the Control Set should simply do nothing, not error.
    ai_observations = session.exec(select(AIVisibilityObservation).where(AIVisibilityObservation.research_run_id == run_b.id)).all()
    assert ai_observations == []


async def test_remeasure_control_set_reissues_baseline_prompt_across_runs(session):
    """The scenario the exit criteria cares about: a recommendation whose
    baseline captured a real AI-visibility prompt must get a fresh
    AIVisibilityObservation for that exact prompt on a later run, even
    though nothing regenerated that PromptVariant this run."""
    store, recommendation, run_b, run_a, intent = await _make_store_recommendation_with_baseline(session)

    stable_intent_id = recommendation.target_intents[0]
    family = PromptFamily(intent_id=intent.id, research_run_id=run_a.id)
    session.add(family)
    session.commit()
    session.refresh(family)
    variant = PromptVariant(prompt_family_id=family.id, text="وش أفضل مطحنة قهوة؟")
    session.add(variant)
    session.commit()
    session.refresh(variant)

    # Simulate what capture_measurement_baseline would have recorded had
    # ai_visibility_agent_run actually produced an observation for run_a.
    from app.models.measurement import MeasurementBaseline

    baseline = session.exec(
        select(MeasurementBaseline).where(MeasurementBaseline.recommendation_id == recommendation.id)
    ).one()
    baseline.target_prompts = [{"stable_intent_id": stable_intent_id, "prompt_variant_id": str(variant.id)}]
    session.add(baseline)
    session.commit()

    surface = AISurface(surface="fake-surface", provider="fake-ai", model="fake-model")
    router = ModelRouter(providers={"fake-ai": FakeAIProvider()})

    await remeasure_control_set(
        session=session, search_provider=FakeSearchProvider(), router=router, store=store,
        recommendation_id=recommendation.id, research_run_id=run_b.id, agent_run_id=None, ai_surfaces=[surface],
    )

    ai_observations = session.exec(
        select(AIVisibilityObservation).where(AIVisibilityObservation.research_run_id == run_b.id)
    ).all()
    assert len(ai_observations) == 1
    assert ai_observations[0].prompt_variant_id == variant.id
    assert ai_observations[0].surface == "fake-surface"
    assert str(ai_observations[0].stable_intent_id) == stable_intent_id


class PoisonousAIProvider(AIProvider):
    """Part Q4 — a real router call in replay mode is exactly the bug this
    proves fixed; any call to .generate() fails the test immediately
    rather than silently succeeding."""

    name = "poisonous-ai"

    async def generate(self, request: AIRequest) -> AIResponse:
        raise AssertionError("real AI provider called during replay mode — Control Set replay is broken")


async def _seed_baseline_prompt(session, recommendation, run_a, intent, stable_intent_id, surface_name="fake-surface"):
    family = PromptFamily(intent_id=intent.id, research_run_id=run_a.id)
    session.add(family)
    session.commit()
    session.refresh(family)
    variant = PromptVariant(prompt_family_id=family.id, text="وش أفضل مطحنة قهوة؟")
    session.add(variant)
    session.commit()
    session.refresh(variant)

    from app.models.measurement import MeasurementBaseline

    baseline = session.exec(
        select(MeasurementBaseline).where(MeasurementBaseline.recommendation_id == recommendation.id)
    ).one()
    baseline.target_prompts = [{"stable_intent_id": stable_intent_id, "prompt_variant_id": str(variant.id)}]
    session.add(baseline)
    session.commit()
    return variant


async def test_remeasure_control_set_replay_mode_never_calls_the_real_router(session):
    """Part Q4 — the exact bug: remeasure_control_set's AI-surface leg
    used to call router.execute_single() unconditionally, with no
    evaluation_mode awareness at all (unlike the SERP leg, which is
    already mode-safe via the get_search_provider factory, and unlike
    run_ai_visibility_agent's own replay branching). In replay mode it
    must reuse a real prior observation instead."""
    store, recommendation, run_b, run_a, intent = await _make_store_recommendation_with_baseline(session)
    stable_intent_id = recommendation.target_intents[0]
    variant = await _seed_baseline_prompt(session, recommendation, run_a, intent, stable_intent_id)

    # A real historical observation for this exact (store, stable_intent,
    # surface) from an earlier run — what replay should find and reuse.
    prior = AIVisibilityObservation(
        store_id=store.id, intent_id=intent.id, stable_intent_id=uuid_from(stable_intent_id),
        prompt_variant_id=variant.id, research_run_id=run_a.id, provider="fake-ai", model="fake-model",
        surface="fake-surface", country="sa", language="ar", mentioned=True, mention_position=3,
    )
    session.add(prior)
    session.commit()
    session.refresh(prior)

    surface = AISurface(surface="fake-surface", provider="fake-ai", model="fake-model")
    router = ModelRouter(providers={"fake-ai": PoisonousAIProvider()})

    await remeasure_control_set(
        session=session, search_provider=FakeSearchProvider(), router=router, store=store,
        recommendation_id=recommendation.id, research_run_id=run_b.id, agent_run_id=None, ai_surfaces=[surface],
        evaluation_mode=EvaluationMode.replay,
    )

    ai_observations = session.exec(
        select(AIVisibilityObservation).where(AIVisibilityObservation.research_run_id == run_b.id)
    ).all()
    assert len(ai_observations) == 1
    assert ai_observations[0].replayed_from_observation_id == prior.id
    assert ai_observations[0].mentioned is True


async def test_remeasure_control_set_replay_mode_skips_when_no_history_exists(session):
    """No real prior observation for this (store, stable_intent, surface)
    exists — replay must skip the cell entirely (never invent data), and
    still never touch the real router."""
    store, recommendation, run_b, run_a, intent = await _make_store_recommendation_with_baseline(session)
    stable_intent_id = recommendation.target_intents[0]
    await _seed_baseline_prompt(session, recommendation, run_a, intent, stable_intent_id)

    surface = AISurface(surface="fake-surface", provider="fake-ai", model="fake-model")
    router = ModelRouter(providers={"fake-ai": PoisonousAIProvider()})

    await remeasure_control_set(
        session=session, search_provider=FakeSearchProvider(), router=router, store=store,
        recommendation_id=recommendation.id, research_run_id=run_b.id, agent_run_id=None, ai_surfaces=[surface],
        evaluation_mode=EvaluationMode.replay,
    )

    ai_observations = session.exec(
        select(AIVisibilityObservation).where(AIVisibilityObservation.research_run_id == run_b.id)
    ).all()
    assert ai_observations == []


def uuid_from(value: str):
    import uuid

    return uuid.UUID(value)
