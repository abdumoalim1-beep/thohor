from dataclasses import dataclass

from app.core.config import Settings
from app.providers.ai.router import ModelRouter


@dataclass(frozen=True)
class AISurface:
    """Provider != model != surface (Part F.5-2). `provider` is the API
    vendor (openai/anthropic/google) — the same one app/providers/ai/
    already talks to. `surface` is the consumer-facing product we're
    measuring visibility on (chatgpt/gemini/claude today). They happen to
    map 1:1 today because that's the only way to reach each surface right
    now, but the split exists so a future surface backed by the *same*
    provider through a *different* product (e.g. Google AI Overviews vs.
    Gemini app, both provider="google") doesn't need a schema change —
    just another AISurface entry."""

    surface: str
    provider: str
    model: str
    search_enabled: bool = False
    grounding_enabled: bool = False
    citations_available: bool = False


# Registry, not a hardcoded switch (same rationale as OPPORTUNITY_DETECTORS,
# RECOMMENDATION_TEMPLATES, CADENCE_INTERVALS elsewhere in this codebase) —
# adding Perplexity/Copilot/a Google AI Overviews surface later is one new
# entry here, no engine code changes. search_enabled/grounding_enabled/
# citations_available are honest capability metadata (Part F.5-14): none of
# the three adapters currently call a web-search/grounding tool, so all
# three are False today — flipping one to True is the explicit, visible act
# of wiring that capability in, never an implicit assumption.
AI_VISIBILITY_SURFACES: list[AISurface] = [
    AISurface(surface="chatgpt", provider="openai", model="gpt-4o-mini"),
    AISurface(surface="gemini", provider="google", model="gemini-2.5-flash"),
    AISurface(surface="claude", provider="anthropic", model="claude-haiku-4-5-20251001"),
]


def resolve_configured_surfaces(router: ModelRouter) -> list[AISurface]:
    """Only surfaces whose underlying provider actually has a key configured
    (mirrors ModelRouter.configured_provider_names / build_providers()'s
    'no key, simply absent' behavior used everywhere else)."""
    configured = set(router.configured_provider_names)
    return [s for s in AI_VISIBILITY_SURFACES if s.provider in configured]


def unavailable_surface_names(settings: Settings) -> list[str]:
    """Surfaces with no API key at all — for API/UI responses that need to
    say 'unavailable / not configured' explicitly (Part F.5 amendment:
    'Unavailable != Zero Visibility' — a surface with no key must never be
    silently treated as 0% in any score or chart). Read-only key check, no
    provider objects constructed — safe to call from a request handler."""
    configured: set[str] = set()
    if settings.openai_api_key:
        configured.add("openai")
    if settings.anthropic_api_key:
        configured.add("anthropic")
    if settings.google_api_key:
        configured.add("google")
    return [s.surface for s in AI_VISIBILITY_SURFACES if s.provider not in configured]
