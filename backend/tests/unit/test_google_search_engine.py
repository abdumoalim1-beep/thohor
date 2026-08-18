"""Google search pass added to multi_engine_runner (SIGNUP-2) — a real
SearchProvider.search() call per question, capped at
GOOGLE_SEARCH_MAX_QUESTIONS, with a deterministic (no AI call) rank-based
analysis. Covers: results persist as sources, the client's own rank is read
correctly, a known competitor's rank is captured, and a provider failure
produces a 'failed' row like every other engine here."""

from app.ai_visibility.multi_engine_runner import (
    GOOGLE_SEARCH_MAX_QUESTIONS,
    build_deterministic_search_analysis,
    create_pending_visibility_run,
    run_visibility_run,
    _select_google_questions,
)
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.models.visibility_run import EngineAnswer, VisibilityQuestion
from app.providers.ai.router import ModelRouter
from app.providers.search.base import SearchProvider, SearchProviderError, SearchRequest, SearchResponse, SearchResultItem
from sqlmodel import select


class FakeSearchProvider(SearchProvider):
    name = "fake_search"

    def __init__(self, results: list[SearchResultItem] | None = None, raise_error: bool = False):
        self._results = results if results is not None else []
        self._raise_error = raise_error

    async def search(self, request: SearchRequest) -> SearchResponse:
        if self._raise_error:
            raise SearchProviderError("search provider unavailable")
        return SearchResponse(provider=self.name, results=self._results)


def _make_store_with_questions(session, count=3, url="https://flowery.example"):
    org = Organization(name="t", slug=f"t-google-{count}-{url}")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url=url)
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)

    for i in range(count):
        session.add(VisibilityQuestion(
            store_id=store.id, text=f"سؤال {i}", category="best",
            normalized_text=f"سؤال {i}", source_research_run_id=run.id,
        ))
    session.commit()
    return store


async def test_google_results_persist_as_sources_on_a_success_row(session):
    store = _make_store_with_questions(session, count=2)
    results = [
        SearchResultItem(rank=1, domain="flowery.example", url="https://flowery.example/p", title="فلاوري"),
        SearchResultItem(rank=2, domain="competitor-site.com", url="https://competitor-site.com/p", title="منافس"),
    ]
    provider = FakeSearchProvider(results=results)
    router = ModelRouter(providers={}, routes={})  # no AI engines configured, isolates the google pass

    pending = create_pending_visibility_run(session, store.id)
    run = await run_visibility_run(session=session, router=router, run=pending, search_provider=provider)

    answers = session.exec(select(EngineAnswer).where(EngineAnswer.visibility_run_id == run.id)).all()
    assert len(answers) == 2  # 2 questions x 1 google pass
    assert all(a.engine == "google" for a in answers)
    assert all(a.status == "success" for a in answers)
    assert all(len(a.sources) == 2 for a in answers)
    assert "google" in run.engines_attempted


async def test_deterministic_analysis_reads_client_rank_and_competitor_rank(session):
    store = _make_store_with_questions(session, count=1, url="https://flowery.example")
    results = [
        SearchResultItem(rank=1, domain="other-site.com", url="https://other-site.com/p", title="غير ذي صلة"),
        SearchResultItem(rank=2, domain="flowery.example", url="https://flowery.example/p", title="فلاوري"),
        SearchResultItem(rank=3, domain="competitor-site.com", url="https://competitor-site.com/p", title="منافس"),
    ]
    provider = FakeSearchProvider(results=results)
    router = ModelRouter(providers={}, routes={})

    pending = create_pending_visibility_run(session, store.id)
    run = await run_visibility_run(session=session, router=router, run=pending, search_provider=provider)
    answer = session.exec(select(EngineAnswer).where(EngineAnswer.visibility_run_id == run.id)).first()

    analysis = build_deterministic_search_analysis(
        answer, client_hostname="flowery.example", competitor_domain_names={"competitor-site.com": "منافس"}
    )

    assert analysis.brand_mentioned is True
    assert analysis.mention_rank == 2
    assert analysis.competitors_mentioned == [{"name": "منافس", "rank": 3}]


def test_deterministic_analysis_honest_when_client_never_appears(session):
    store = _make_store_with_questions(session, count=1)
    answer = EngineAnswer(
        visibility_run_id=store.id, question_id=store.id, store_id=store.id,  # ids irrelevant to this pure function
        engine="google", engine_model="serpapi", status="success",
        sources=[{"url": "https://other-site.com/p", "title": "غير ذي صلة"}],
    )

    analysis = build_deterministic_search_analysis(
        answer, client_hostname="flowery.example", competitor_domain_names={}
    )

    assert analysis.brand_mentioned is False
    assert analysis.mention_type == "not_mentioned"
    assert analysis.mention_rank is None


async def test_google_provider_failure_produces_a_failed_row_never_aborts(session):
    store = _make_store_with_questions(session, count=2)
    provider = FakeSearchProvider(raise_error=True)
    router = ModelRouter(providers={}, routes={})

    pending = create_pending_visibility_run(session, store.id)
    run = await run_visibility_run(session=session, router=router, run=pending, search_provider=provider)

    answers = session.exec(select(EngineAnswer).where(EngineAnswer.visibility_run_id == run.id)).all()
    assert len(answers) == 2
    assert all(a.status == "failed" for a in answers)


async def test_google_pass_capped_at_max_questions(session):
    store = _make_store_with_questions(session, count=GOOGLE_SEARCH_MAX_QUESTIONS + 10)
    provider = FakeSearchProvider(results=[])
    router = ModelRouter(providers={}, routes={})

    pending = create_pending_visibility_run(session, store.id)
    run = await run_visibility_run(session=session, router=router, run=pending, search_provider=provider)

    answers = session.exec(select(EngineAnswer).where(EngineAnswer.visibility_run_id == run.id)).all()
    assert len(answers) == GOOGLE_SEARCH_MAX_QUESTIONS


async def test_no_search_provider_means_no_google_pass_at_all(session):
    store = _make_store_with_questions(session, count=2)
    router = ModelRouter(providers={}, routes={})

    pending = create_pending_visibility_run(session, store.id)
    run = await run_visibility_run(session=session, router=router, run=pending)  # search_provider omitted

    answers = session.exec(select(EngineAnswer).where(EngineAnswer.visibility_run_id == run.id)).all()
    assert answers == []
    assert run.engines_attempted == []


def _q(category: str, n: int) -> VisibilityQuestion:
    import uuid
    return VisibilityQuestion(
        store_id=uuid.uuid4(), text=f"{category} {n}", category=category,
        normalized_text=f"{category} {n}", source_research_run_id=uuid.uuid4(),
    )


def test_select_google_questions_prioritizes_purchase_intent_categories():
    """User direction: Google's subset should prioritize نية الشراء
    (recommendation), local, product_discovery, comparison, alternatives,
    price/occasion — over 'best'/'problem_solution' — when there are more
    candidates than the budget allows."""
    questions = (
        [_q("best", i) for i in range(20)]
        + [_q("recommendation", i) for i in range(5)]
        + [_q("local", i) for i in range(5)]
        + [_q("problem_solution", i) for i in range(20)]
    )

    selected = _select_google_questions(questions, limit=10)

    assert len(selected) == 10
    assert {q.category for q in selected} == {"recommendation", "local"}


def test_select_google_questions_falls_back_to_remaining_categories_if_priority_ones_dont_fill_budget():
    questions = [_q("recommendation", i) for i in range(3)] + [_q("best", i) for i in range(10)]

    selected = _select_google_questions(questions, limit=10)

    assert len(selected) == 10
    assert sum(1 for q in selected if q.category == "recommendation") == 3
    assert sum(1 for q in selected if q.category == "best") == 7
