import pytest
from sqlmodel import select

from app.models.intent import Intent, IntentSource, Keyword
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
from app.models.store import Store
from app.providers.search.base import SearchProviderError, SearchRequest
from app.providers.search.replay_provider import ReplaySearchProvider


def _seed_store_run(session):
    org = Organization(name="t", slug="t-replay")
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
    intent = Intent(
        store_id=store.id, research_run_id=run.id, topic="topic",
        country="sa", language="ar", source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    return store, run, intent


def _seed_keyword(session, text, country="sa", language="ar"):
    keyword = Keyword(text=text, country=country, language=language)
    session.add(keyword)
    session.commit()
    session.refresh(keyword)
    return keyword


async def test_replay_returns_real_historical_results(session):
    store, run, intent = _seed_store_run(session)
    keyword = _seed_keyword(session, "قهوة مختصة")
    session.add(
        SerpObservation(
            store_id=store.id, intent_id=intent.id, keyword_id=keyword.id, research_run_id=run.id,
            country="sa", language="ar",
            results=[{"rank": 1, "domain": "rival.test", "url": "https://rival.test/x", "title": "أفضل قهوة"}],
        )
    )
    session.commit()

    provider = ReplaySearchProvider(session)
    response = await provider.search(SearchRequest(keyword="قهوة مختصة", country="sa", language="ar"))

    assert response.provider == "replay"
    assert len(response.results) == 1
    assert response.results[0].domain == "rival.test"
    assert response.raw["replay"] is True


async def test_replay_picks_most_recent_observation(session):
    store, run, intent = _seed_store_run(session)
    keyword = _seed_keyword(session, "قهوة مختصة")
    session.add(
        SerpObservation(
            store_id=store.id, intent_id=intent.id, keyword_id=keyword.id, research_run_id=run.id,
            country="sa", language="ar", results=[{"rank": 1, "domain": "old.test", "url": "https://old.test"}],
        )
    )
    session.commit()
    session.add(
        SerpObservation(
            store_id=store.id, intent_id=intent.id, keyword_id=keyword.id, research_run_id=run.id,
            country="sa", language="ar", results=[{"rank": 1, "domain": "new.test", "url": "https://new.test"}],
        )
    )
    session.commit()

    provider = ReplaySearchProvider(session)
    response = await provider.search(SearchRequest(keyword="قهوة مختصة", country="sa", language="ar"))

    assert response.results[0].domain == "new.test"


async def test_replay_raises_when_no_keyword_match(session):
    provider = ReplaySearchProvider(session)
    with pytest.raises(SearchProviderError):
        await provider.search(SearchRequest(keyword="غير موجود", country="sa", language="ar"))


async def test_replay_raises_when_keyword_exists_but_no_observation(session):
    _seed_keyword(session, "كلمة بلا نتائج")
    provider = ReplaySearchProvider(session)
    with pytest.raises(SearchProviderError):
        await provider.search(SearchRequest(keyword="كلمة بلا نتائج", country="sa", language="ar"))
