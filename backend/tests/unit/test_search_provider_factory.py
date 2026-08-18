import pytest

from app.core.config import Settings
from app.core.evaluation_mode import EvaluationMode, LiveProviderBlockedError
from app.providers.search import get_search_provider
from app.providers.search.mock_provider import MockSearchProvider
from app.providers.search.replay_provider import ReplaySearchProvider
from app.providers.search.serpapi_provider import SerpApiProvider


def _settings(**overrides) -> Settings:
    defaults = dict(serpapi_api_key=None, dev_live_serp_budget=0, live_serp_override=False)
    defaults.update(overrides)
    return Settings(**defaults)


def test_mock_mode_returns_mock_provider_without_session(monkeypatch):
    monkeypatch.setattr("app.providers.search.get_settings", lambda: _settings(evaluation_mode=EvaluationMode.mock))
    provider = get_search_provider()
    assert isinstance(provider, MockSearchProvider)


def test_replay_mode_requires_a_session(monkeypatch):
    monkeypatch.setattr("app.providers.search.get_settings", lambda: _settings(evaluation_mode=EvaluationMode.replay))
    with pytest.raises(ValueError):
        get_search_provider()


def test_replay_mode_returns_replay_provider_with_session(monkeypatch, session):
    monkeypatch.setattr("app.providers.search.get_settings", lambda: _settings(evaluation_mode=EvaluationMode.replay))
    provider = get_search_provider(session)
    assert isinstance(provider, ReplaySearchProvider)


def test_live_mode_blocked_without_key(monkeypatch):
    monkeypatch.setattr(
        "app.providers.search.get_settings",
        lambda: _settings(evaluation_mode=EvaluationMode.live, serpapi_api_key=None),
    )
    with pytest.raises(LiveProviderBlockedError):
        get_search_provider()


def test_live_mode_blocked_by_zero_budget_guard_even_with_key(monkeypatch):
    monkeypatch.setattr(
        "app.providers.search.get_settings",
        lambda: _settings(evaluation_mode=EvaluationMode.live, serpapi_api_key="fake-key", dev_live_serp_budget=0, live_serp_override=False),
    )
    with pytest.raises(LiveProviderBlockedError):
        get_search_provider()


def test_live_mode_allowed_with_explicit_budget(monkeypatch):
    monkeypatch.setattr(
        "app.providers.search.get_settings",
        lambda: _settings(evaluation_mode=EvaluationMode.live, serpapi_api_key="fake-key", dev_live_serp_budget=10),
    )
    provider = get_search_provider()
    assert isinstance(provider, SerpApiProvider)


def test_live_mode_allowed_with_explicit_override(monkeypatch):
    monkeypatch.setattr(
        "app.providers.search.get_settings",
        lambda: _settings(evaluation_mode=EvaluationMode.live, serpapi_api_key="fake-key", live_serp_override=True),
    )
    provider = get_search_provider()
    assert isinstance(provider, SerpApiProvider)
