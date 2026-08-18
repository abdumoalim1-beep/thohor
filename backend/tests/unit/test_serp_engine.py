import asyncio

from sqlmodel import select

from app.intent.intent_engine import _attach_keywords
from app.models.evidence import Evidence
from app.models.intent import Intent, IntentSource
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.serp import SerpExecution, SerpExecutionStatus, SerpObservation
from app.models.store import Store
from app.providers.search.base import SearchProvider, SearchProviderError, SearchRequest, SearchResponse, SearchResultItem
from app.serp.metrics import compute_visibility_metrics
from app.serp.serp_engine import run_serp_agent, select_balanced_intents


def test_query_selection_is_balanced_across_product_categories():
    intents = [
        *[Intent(topic=f"عين {i}", category="العيون", country="sa", language="ar", source=IntentSource.deterministic_catalog) for i in range(5)],
        Intent(topic="روج", category="الشفاه", country="sa", language="ar", source=IntentSource.deterministic_catalog),
        Intent(topic="بودرة", category="الوجه", country="sa", language="ar", source=IntentSource.deterministic_catalog),
    ]
    selected = select_balanced_intents(intents, 3)
    assert {item.category for item in selected} == {"العيون", "الشفاه", "الوجه"}


class FakeSearchProvider(SearchProvider):
    name = "fake_search"

    async def search(self, request: SearchRequest) -> SearchResponse:
        if request.keyword == "found me":
            results = [
                SearchResultItem(rank=1, domain="other.test", url="https://other.test/x"),
                SearchResultItem(rank=2, domain="another.test", url="https://another.test/y"),
                SearchResultItem(rank=3, domain="store.example", url="https://store.example/product"),
            ]
        elif request.keyword == "not found":
            results = [SearchResultItem(rank=1, domain="other.test", url="https://other.test/x")]
        else:
            raise SearchProviderError("simulated SERP outage")
        return SearchResponse(provider=self.name, results=results, latency_ms=5)


class FakeSerpApiProvider(SearchProvider):
    """Named 'serpapi' to exercise the real per-search cost estimate (Part
    F.5-12) and raw artifact archiving (Part F.5-1) — without hitting the
    network."""

    name = "serpapi"

    async def search(self, request: SearchRequest) -> SearchResponse:
        results = [SearchResultItem(rank=1, domain="store.example", url="https://store.example/x")]
        return SearchResponse(provider=self.name, results=results, raw={"organic_results": []}, latency_ms=5)


class FakeStorage:
    def __init__(self):
        self.saved: list[tuple[str, str]] = []

    def put_text(self, key_prefix: str, content: str, content_type: str = "text/html") -> str:
        self.saved.append((key_prefix, content))
        return f"s3://fake-bucket/{key_prefix}/0"


def _make_store_with_intents(session):
    org = Organization(name="t", slug="t-serp")
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

    intents = []
    for topic, keyword in [("found topic", "found me"), ("missing topic", "not found")]:
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
        _attach_keywords(session, intent, [keyword], "sa", "ar")
        intents.append(intent)

    return store, run, intents


async def test_serp_agent_finds_client_rank_and_records_evidence(session):
    store, run, intents = _make_store_with_intents(session)

    observations = await run_serp_agent(
        session=session,
        search_provider=FakeSearchProvider(),
        store_id=store.id,
        store_url=store.url,
        research_run_id=run.id,
        agent_run_id=None,
        intents=intents,
        country="sa",
        language="ar",
        num_results=10,
        max_queries=10,
    )

    assert len(observations) == 2
    found = next(o for o in observations if o.client_rank is not None)
    missing = next(o for o in observations if o.client_rank is None)

    assert found.client_rank == 3
    assert found.client_url == "https://store.example/product"
    assert missing.client_rank is None

    executions = session.exec(select(SerpExecution)).all()
    assert len(executions) == 2
    assert all(e.status == SerpExecutionStatus.success for e in executions)

    evidence = session.exec(select(Evidence)).all()
    assert len(evidence) == 2


async def test_serp_agent_logs_error_execution_without_observation(session):
    store, run, intents = _make_store_with_intents(session)
    intent = Intent(
        store_id=store.id,
        research_run_id=run.id,
        topic="broken topic",
        country="sa",
        language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    _attach_keywords(session, intent, ["trigger error"], "sa", "ar")

    observations = await run_serp_agent(
        session=session,
        search_provider=FakeSearchProvider(),
        store_id=store.id,
        store_url=store.url,
        research_run_id=run.id,
        agent_run_id=None,
        intents=[intent],
        country="sa",
        language="ar",
        num_results=10,
        max_queries=10,
    )

    assert observations == []
    execution = session.exec(select(SerpExecution)).one()
    assert execution.status == SerpExecutionStatus.error


async def test_compute_visibility_metrics(session):
    store, run, intents = _make_store_with_intents(session)
    await run_serp_agent(
        session=session,
        search_provider=FakeSearchProvider(),
        store_id=store.id,
        store_url=store.url,
        research_run_id=run.id,
        agent_run_id=None,
        intents=intents,
        country="sa",
        language="ar",
        num_results=10,
        max_queries=10,
    )

    metrics = compute_visibility_metrics(session, run.id)

    assert metrics.total_intents_measured == 2
    assert metrics.ranking_coverage == 0.5
    assert metrics.top3_rate == 0.5
    assert metrics.top10_rate == 0.5
    assert metrics.avg_client_rank == 3


async def test_serp_agent_records_real_cost_and_raw_artifact_for_serpapi_provider(session):
    store, run, intents = _make_store_with_intents(session)
    storage = FakeStorage()

    observations = await run_serp_agent(
        session=session,
        search_provider=FakeSerpApiProvider(),
        store_id=store.id,
        store_url=store.url,
        research_run_id=run.id,
        agent_run_id=None,
        intents=intents[:1],
        country="sa",
        language="ar",
        num_results=10,
        max_queries=1,
        storage=storage,
    )

    assert len(observations) == 1
    assert observations[0].raw_artifact_uri is not None
    assert len(storage.saved) == 1

    execution = session.exec(select(SerpExecution)).one()
    assert execution.cost_usd == 0.01  # Part F.5-12 estimated per-search cost for provider "serpapi"


class ConcurrencyTrackingProvider(SearchProvider):
    """Part H5 — records how many searches were in flight at once, so tests
    can prove independent queries genuinely overlap instead of running one
    at a time."""

    name = "tracking"

    def __init__(self):
        self.in_flight = 0
        self.peak_in_flight = 0

    async def search(self, request: SearchRequest) -> SearchResponse:
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        await asyncio.sleep(0.05)
        self.in_flight -= 1
        return SearchResponse(provider=self.name, results=[SearchResultItem(rank=1, domain="x.test", url="https://x.test")])


def _make_store_with_n_intents(session, n: int):
    org = Organization(name="t", slug=f"t-serp-concurrency-{n}")
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

    intents = []
    for i in range(n):
        intent = Intent(
            store_id=store.id, research_run_id=run.id, topic=f"topic-{i}", country="sa", language="ar",
            source=IntentSource.deterministic_catalog,
        )
        session.add(intent)
        session.commit()
        session.refresh(intent)
        _attach_keywords(session, intent, [f"keyword-{i}"], "sa", "ar")
        intents.append(intent)
    return store, run, intents


async def test_serp_agent_runs_independent_queries_concurrently(session):
    store, run, intents = _make_store_with_n_intents(session, 4)
    provider = ConcurrencyTrackingProvider()

    observations = await run_serp_agent(
        session=session, search_provider=provider, store_id=store.id, store_url=store.url,
        research_run_id=run.id, agent_run_id=None, intents=intents, country="sa", language="ar",
        num_results=10, max_queries=10, max_concurrency=4,
    )

    assert len(observations) == 4
    # All 4 queries genuinely overlapped — proof this isn't A -> wait -> B -> wait -> C.
    assert provider.peak_in_flight == 4


async def test_serp_agent_respects_max_concurrency_ceiling(session):
    store, run, intents = _make_store_with_n_intents(session, 6)
    provider = ConcurrencyTrackingProvider()

    await run_serp_agent(
        session=session, search_provider=provider, store_id=store.id, store_url=store.url,
        research_run_id=run.id, agent_run_id=None, intents=intents, country="sa", language="ar",
        num_results=10, max_queries=10, max_concurrency=2,
    )

    # Never more than 2 in flight at once, even with 6 independent queries.
    assert provider.peak_in_flight == 2
