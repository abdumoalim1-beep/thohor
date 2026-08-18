"""Part 2 MVP — answer_analysis_engine + visibility_metrics_v2. Covers:
structured classification persists with the evidence quote intact, a
provider failure degrades to None (never blocks the run), skipping a
failed EngineAnswer entirely (nothing to analyze), and the 8 core metrics
computed correctly from a small, hand-built set of analyses — including the
'no evidence yet -> None, never a fabricated 0.0' rule."""

import json

from app.ai_visibility.answer_analysis_engine import analyze_engine_answer
from app.ai_visibility.visibility_metrics_v2 import (
    compute_client_rank_among_competitors,
    compute_top_citations,
    compute_top_competitors,
    compute_visibility_metrics,
)
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.models.visibility_run import EngineAnswer, EngineAnswerAnalysis, VisibilityQuestion, VisibilityRun
from app.providers.ai.base import AIProvider, AIProviderError, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute
from app.schemas.answer_analysis import AnswerAnalysisResult


class FakeAnalysisProvider(AIProvider):
    name = "fake_analysis"

    def __init__(self, payload: dict | None = None, raise_error: bool = False):
        self._payload = payload
        self._raise_error = raise_error
        self.last_request: AIRequest | None = None

    async def generate(self, request: AIRequest) -> AIResponse:
        self.last_request = request
        if self._raise_error:
            raise AIProviderError("provider unavailable")
        return AIResponse(
            provider=self.name, model=request.model, text=json.dumps(self._payload),
            usage=AIUsage(input_tokens=10, output_tokens=10),
        )


def _router(provider: AIProvider) -> ModelRouter:
    return ModelRouter(providers={"fake": provider}, routes={"answer_analysis": TaskRoute(primary=ModelChoice("fake", "fake-model"))})


def _make_store(session):
    org = Organization(name="t", slug="t-analysis")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://flowery.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


def _make_answer(session, store, *, status="success", raw_answer="نص الإجابة"):
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    question = VisibilityQuestion(
        store_id=store.id, text="ما أفضل متجر ورد؟", category="best",
        normalized_text="ما افضل متجر ورد", source_research_run_id=run.id,
    )
    session.add(question)
    session.commit()
    session.refresh(question)
    visibility_run = VisibilityRun(store_id=store.id, status="completed")
    session.add(visibility_run)
    session.commit()
    session.refresh(visibility_run)
    answer = EngineAnswer(
        visibility_run_id=visibility_run.id, question_id=question.id, store_id=store.id,
        engine="chatgpt", engine_model="gpt-4o-mini", status=status, raw_answer=raw_answer,
    )
    session.add(answer)
    session.commit()
    session.refresh(answer)
    return visibility_run, question, answer


_VALID_ANALYSIS = {
    "brand_mentioned": True, "mention_type": "recommended", "mention_rank": 1, "recommendation_rank": 1,
    "competitors_mentioned": [{"name": "منافس أ", "rank": 2}],
    "evidence_quote": "أنصحك بفلاوري لباقات الورد", "confidence": 0.92,
}


async def test_successful_analysis_persists_with_evidence_quote(session):
    store = _make_store(session)
    _run, _question, answer = _make_answer(session, store)
    provider = FakeAnalysisProvider(payload=_VALID_ANALYSIS)

    analysis = await analyze_engine_answer(
        session=session, router=_router(provider), engine_answer=answer, question_text="ما أفضل متجر ورد؟",
        brand_name="فلاوري", competitor_names=["منافس أ"],
    )

    assert analysis is not None
    assert analysis.brand_mentioned is True
    assert analysis.mention_type == "recommended"
    assert analysis.evidence_quote == "أنصحك بفلاوري لباقات الورد"
    assert analysis.competitors_mentioned == [{"name": "منافس أ", "rank": 2}]


async def test_brand_aliases_are_folded_into_the_grounding_prompt(session):
    """Once a user confirms/edits a name (POST /stores/{id}/brand-name),
    the previous name and the store's domain become aliases — this must
    actually reach the AI prompt, not just sit unused in the DB, or an
    answer that still says the old name would be missed."""
    store = _make_store(session)
    _run, _question, answer = _make_answer(session, store)
    provider = FakeAnalysisProvider(payload=_VALID_ANALYSIS)

    await analyze_engine_answer(
        session=session, router=_router(provider), engine_answer=answer, question_text="ما أفضل متجر ورد؟",
        brand_name="فلاوري", competitor_names=[], brand_aliases=["Flowery", "flowery.sa"],
    )

    assert provider.last_request is not None
    rendered = " ".join(m.content for m in provider.last_request.messages)
    assert "فلاوري" in rendered
    assert "Flowery" in rendered
    assert "flowery.sa" in rendered


async def test_no_aliases_leaves_the_prompt_unchanged(session):
    """brand_aliases is purely additive — omitting it (the pre-existing
    call shape) must render exactly as before, no stray alias text."""
    store = _make_store(session)
    _run, _question, answer = _make_answer(session, store)
    provider = FakeAnalysisProvider(payload=_VALID_ANALYSIS)

    await analyze_engine_answer(
        session=session, router=_router(provider), engine_answer=answer, question_text="ما أفضل متجر ورد؟",
        brand_name="فلاوري", competitor_names=[],
    )

    rendered = " ".join(m.content for m in provider.last_request.messages)
    assert "يُعرف أيضًا" not in rendered


async def test_failed_answer_is_never_sent_for_analysis(session):
    store = _make_store(session)
    _run, _question, answer = _make_answer(session, store, status="failed", raw_answer=None)
    provider = FakeAnalysisProvider(payload=_VALID_ANALYSIS)

    analysis = await analyze_engine_answer(
        session=session, router=_router(provider), engine_answer=answer, question_text="ما أفضل متجر ورد؟",
        brand_name="فلاوري", competitor_names=[],
    )

    assert analysis is None


async def test_provider_failure_degrades_to_none(session):
    store = _make_store(session)
    _run, _question, answer = _make_answer(session, store)
    provider = FakeAnalysisProvider(raise_error=True)

    analysis = await analyze_engine_answer(
        session=session, router=_router(provider), engine_answer=answer, question_text="ما أفضل متجر ورد؟",
        brand_name="فلاوري", competitor_names=[],
    )

    assert analysis is None


def test_metrics_are_none_not_zero_when_nothing_analyzed_yet(session):
    store = _make_store(session)
    visibility_run, _question, _answer = _make_answer(session, store)

    metrics = compute_visibility_metrics(session, visibility_run.id, "flowery.example")

    assert metrics.mention_rate is None
    assert metrics.recommendation_rate is None
    assert metrics.share_of_voice is None


def test_metrics_computed_correctly_from_a_small_analyzed_set(session):
    store = _make_store(session)
    visibility_run, _question, answer = _make_answer(session, store)

    session.add(EngineAnswerAnalysis(
        engine_answer_id=answer.id, store_id=store.id, brand_mentioned=True, mention_type="recommended",
        mention_rank=1, recommendation_rank=1, competitors_mentioned=[{"name": "منافس أ"}], confidence=0.9,
    ))
    session.commit()

    # A second answer in the same run, mentioned but not recommended.
    _run2, question2, answer2 = _make_answer(session, store)
    answer2.visibility_run_id = visibility_run.id
    session.add(answer2)
    session.commit()
    session.add(EngineAnswerAnalysis(
        engine_answer_id=answer2.id, store_id=store.id, brand_mentioned=True, mention_type="mere_mention",
        competitors_mentioned=[{"name": "منافس أ"}, {"name": "منافس ب"}], confidence=0.7,
    ))
    session.commit()

    metrics = compute_visibility_metrics(session, visibility_run.id, "flowery.example")

    assert metrics.successful_answers == 2
    assert metrics.mention_rate == 1.0  # both mentioned
    assert metrics.recommendation_rate == 0.5  # only 1 of 2 recommended
    assert metrics.avg_recommendation_rank == 1.0
    assert metrics.top_3_rate == 0.5
    # client_mentions=2, competitor_mentions=3 (1 + 2) -> 2/5
    assert metrics.share_of_voice == 0.4
    assert metrics.top_competitor == "منافس أ"
    assert metrics.top_competitor_mentions == 2
    assert metrics.mentioned_count == 2
    assert metrics.avg_mention_rank == 1.0  # only answer 1 has a mention_rank (1)
    assert metrics.top3_count == 1


def test_total_searches_counts_failed_attempts_too_but_rates_dont(session):
    """SIGNUP re-scope: 'X من 160+' must reflect everything attempted
    (success + failed), but appearance rates must stay scoped to the
    honestly-analyzable successful set — a technical failure must never
    silently drag the appearance rate down."""
    store = _make_store(session)
    visibility_run, _question, answer = _make_answer(session, store)
    session.add(EngineAnswerAnalysis(
        engine_answer_id=answer.id, store_id=store.id, brand_mentioned=True, mention_type="mere_mention",
        mention_rank=2, confidence=0.9,
    ))
    session.commit()

    run2, _q2, failed_answer = _make_answer(session, store, status="failed", raw_answer=None)
    failed_answer.visibility_run_id = visibility_run.id
    session.add(failed_answer)
    session.commit()

    metrics = compute_visibility_metrics(session, visibility_run.id, "flowery.example")

    assert metrics.total_searches == 2  # 1 success + 1 failed
    assert metrics.successful_answers == 1
    assert metrics.mention_rate == 1.0  # rate is over the successful/analyzed set only


def test_compute_top_competitors_ranks_by_appearances_and_flags_ahead(session):
    store = _make_store(session)
    visibility_run, _question, answer = _make_answer(session, store)
    session.add(EngineAnswerAnalysis(
        engine_answer_id=answer.id, store_id=store.id, brand_mentioned=True, mention_type="mere_mention",
        mention_rank=3, competitors_mentioned=[{"name": "منافس قوي", "rank": 1}, {"name": "منافس ضعيف", "rank": 5}],
        confidence=0.9,
    ))
    session.commit()

    top = compute_top_competitors(
        session, visibility_run.id, client_avg_mention_rank=3.0,
        competitor_name_to_domain={"منافس قوي": "strong-competitor.com"},
    )

    assert len(top) == 2
    strong = next(c for c in top if c.name == "منافس قوي")
    weak = next(c for c in top if c.name == "منافس ضعيف")
    assert strong.domain == "strong-competitor.com"
    assert strong.avg_rank == 1.0
    assert strong.ahead_of_client is True  # rank 1 beats client's rank 3
    assert weak.ahead_of_client is False  # rank 5 is behind the client


def test_compute_top_citations_excludes_search_and_social_and_flags_supports(session):
    store = _make_store(session)
    visibility_run, _question, answer = _make_answer(session, store)
    answer.sources = [
        {"url": "https://www.google.com/maps/place/x", "title": "خرائط جوجل"},
        {"url": "https://www.instagram.com/somebrand", "title": "انستغرام"},
        {"url": "https://real-review-site.com/article", "title": "مراجعة"},
        {"url": "https://competitor-a.com/products", "title": "منافس أ"},
    ]
    session.add(answer)
    session.commit()
    session.add(EngineAnswerAnalysis(
        engine_answer_id=answer.id, store_id=store.id, brand_mentioned=True, mention_type="mere_mention",
        mention_rank=2, confidence=0.9,
    ))
    session.commit()

    citations = compute_top_citations(
        session, visibility_run.id, client_hostname="flowery.example",
        competitor_domain_names={"منافس أ": "competitor-a.com"},
    )

    domains = {c.domain for c in citations}
    assert "google.com" not in domains  # Google Maps/search — excluded
    assert "instagram.com" not in domains  # social platform — excluded
    assert "real-review-site.com" in domains
    assert "competitor-a.com" in domains

    review = next(c for c in citations if c.domain == "real-review-site.com")
    assert review.supports == "client"  # this answer mentioned the brand

    competitor_citation = next(c for c in citations if c.domain == "competitor-a.com")
    assert competitor_citation.supports == "competitor"  # a known competitor's own storefront


def test_compute_client_rank_among_competitors_counts_who_beats_the_client():
    rank, total = compute_client_rank_among_competitors(5, [10, 3, 1])
    assert rank == 2  # only the appearances=10 competitor beats the client's 5
    assert total == 4  # 3 competitors + the client itself


def test_compute_client_rank_among_competitors_ties_share_the_better_rank():
    rank, total = compute_client_rank_among_competitors(5, [5, 5, 1])
    assert rank == 1  # equal appearances is not "ahead", so the client still ranks 1st
    assert total == 4


def test_mention_rank_of_zero_is_clamped_to_none_never_trusted_as_rank_one():
    """Programmatic enforcement, not just the prompt: a model returning
    mention_rank=0 must never be persisted as a real rank."""
    result = AnswerAnalysisResult(
        brand_mentioned=True, mention_type="mere_mention", mention_rank=0, recommendation_rank=0, confidence=0.5,
    )
    assert result.mention_rank is None
    assert result.recommendation_rank is None
