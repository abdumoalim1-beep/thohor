from app.core.config import Settings
from app.models.research_task import TaskType
from app.providers.ai.base import AIProvider, AIRequest, AIResponse
from app.providers.ai.router import ModelRouter
from app.research.capabilities import ResearchCapabilities, resolve_research_capabilities


class _FakeProvider(AIProvider):
    def __init__(self, name: str):
        self.name = name

    async def generate(self, request: AIRequest) -> AIResponse:
        raise NotImplementedError


def _settings(**overrides) -> Settings:
    # serpapi_api_key defaults to None explicitly — Settings() otherwise
    # picks up the real .env in this dev environment, which has a live key
    # configured, making search_configured assertions flaky.
    defaults = dict(serpapi_api_key=None)
    defaults.update(overrides)
    return Settings(**defaults)


def test_resolve_research_capabilities_reflects_only_configured_providers():
    router = ModelRouter(providers={"openai": _FakeProvider("openai")})
    capabilities = resolve_research_capabilities(router, _settings())

    assert capabilities.configured_ai_surfaces == frozenset({"chatgpt"})
    assert capabilities.any_ai_surface_configured is True
    assert capabilities.search_configured is False


def test_resolve_research_capabilities_with_no_ai_provider_configured():
    router = ModelRouter(providers={})
    capabilities = resolve_research_capabilities(router, _settings())

    assert capabilities.configured_ai_surfaces == frozenset()
    assert capabilities.any_ai_surface_configured is False


def test_unavailable_task_types_excludes_only_unconfigured_surfaces():
    capabilities = ResearchCapabilities(configured_ai_surfaces=frozenset({"chatgpt"}), search_configured=False)
    unavailable = capabilities.unavailable_task_types()

    assert TaskType.ai_visibility_gemini in unavailable
    assert TaskType.ai_visibility_claude in unavailable
    assert TaskType.ai_visibility_chatgpt not in unavailable
    # At least one AI surface (chatgpt) is configured, so cross-surface
    # validation is still meaningful.
    assert TaskType.validate_cross_surface_finding not in unavailable
    assert capabilities.is_task_type_available(TaskType.ai_visibility_chatgpt) is True
    assert capabilities.is_task_type_available(TaskType.ai_visibility_gemini) is False


def test_validate_cross_surface_finding_unavailable_with_no_ai_surface_at_all():
    capabilities = ResearchCapabilities(configured_ai_surfaces=frozenset(), search_configured=True)
    unavailable = capabilities.unavailable_task_types()

    assert TaskType.validate_cross_surface_finding in unavailable
    assert TaskType.ai_visibility_chatgpt in unavailable
    assert TaskType.ai_visibility_gemini in unavailable
    assert TaskType.ai_visibility_claude in unavailable
    # Non-AI task types are never gated by capabilities.
    assert capabilities.is_task_type_available(TaskType.competitor_deep_dive) is True
    assert capabilities.is_task_type_available(TaskType.search_google) is True


def test_all_surfaces_configured_leaves_nothing_unavailable():
    capabilities = ResearchCapabilities(
        configured_ai_surfaces=frozenset({"chatgpt", "gemini", "claude"}), search_configured=True
    )
    assert capabilities.unavailable_task_types() == frozenset()
