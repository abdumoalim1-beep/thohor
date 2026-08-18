from functools import lru_cache

from app.core.config import get_settings
from app.providers.ai.factory import build_providers
from app.providers.ai.router import ModelRouter

__all__ = ["ModelRouter", "get_router"]


@lru_cache
def get_router() -> ModelRouter:
    settings = get_settings()
    providers = build_providers(settings)
    return ModelRouter(providers=providers)
