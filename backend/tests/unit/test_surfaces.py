from app.ai_visibility.surfaces import AI_VISIBILITY_SURFACES, resolve_configured_surfaces, unavailable_surface_names
from app.core.config import Settings
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelRouter


class FakeProvider(AIProvider):
    name = "fake"

    async def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(provider=self.name, model=request.model, text="", usage=AIUsage())


def test_resolve_configured_surfaces_only_returns_surfaces_with_a_configured_provider():
    router = ModelRouter(providers={"openai": FakeProvider()})
    resolved = resolve_configured_surfaces(router)
    assert [s.surface for s in resolved] == ["chatgpt"]


def test_resolve_configured_surfaces_empty_when_no_providers_configured():
    router = ModelRouter(providers={})
    assert resolve_configured_surfaces(router) == []


def test_resolve_configured_surfaces_returns_all_three_when_all_providers_configured():
    router = ModelRouter(providers={"openai": FakeProvider(), "anthropic": FakeProvider(), "google": FakeProvider()})
    resolved = resolve_configured_surfaces(router)
    assert {s.surface for s in resolved} == {"chatgpt", "gemini", "claude"}


def test_ai_visibility_surfaces_registry_has_distinct_provider_model_per_surface():
    surfaces = {s.surface for s in AI_VISIBILITY_SURFACES}
    assert surfaces == {"chatgpt", "gemini", "claude"}
    for surface in AI_VISIBILITY_SURFACES:
        assert surface.search_enabled is False  # honest V1 default — see Part F.5-14
        assert surface.grounding_enabled is False


def test_unavailable_surface_names_lists_only_surfaces_without_a_key():
    settings = Settings(openai_api_key="sk-fake", anthropic_api_key=None, google_api_key=None)
    assert unavailable_surface_names(settings) == ["gemini", "claude"]


def test_unavailable_surface_names_empty_when_all_keys_present():
    settings = Settings(openai_api_key="a", anthropic_api_key="b", google_api_key="c")
    assert unavailable_surface_names(settings) == []


def test_unavailable_surface_names_all_three_when_no_keys():
    settings = Settings(openai_api_key=None, anthropic_api_key=None, google_api_key=None)
    assert set(unavailable_surface_names(settings)) == {"chatgpt", "gemini", "claude"}
