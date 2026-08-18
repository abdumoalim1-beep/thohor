from app.core.config import Settings
from app.providers.ai.anthropic_provider import AnthropicProvider
from app.providers.ai.base import AIProvider
from app.providers.ai.google_provider import GoogleProvider
from app.providers.ai.mock_provider import MockAIProvider
from app.providers.ai.openai_provider import OpenAIProvider


def build_providers(settings: Settings) -> dict[str, AIProvider]:
    """Build the set of available providers from configured API keys. A
    provider with no key configured is simply absent — the router raises a
    clear error only if a route actually needs it, instead of failing at
    startup for keys nobody is using yet."""
    providers: dict[str, AIProvider] = {"mock": MockAIProvider()}

    if settings.openai_api_key:
        providers["openai"] = OpenAIProvider(api_key=settings.openai_api_key.get_secret_value())
    if settings.anthropic_api_key:
        providers["anthropic"] = AnthropicProvider(api_key=settings.anthropic_api_key.get_secret_value())
    if settings.google_api_key:
        providers["google"] = GoogleProvider(api_key=settings.google_api_key.get_secret_value())

    return providers
