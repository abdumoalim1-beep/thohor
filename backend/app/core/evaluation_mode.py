from enum import Enum


class EvaluationMode(str, Enum):
    """How this process is allowed to source SERP/AI-visibility data.

    mock: synthetic, network-free data — unit tests only.
    replay: real historical observations already in the DB (serp_observations,
      ai_visibility_observations, ...) served as-is, zero new network calls.
      Not mock data — genuinely-measured data, just not freshly measured.
    live: real provider calls, real cost. Gated by an explicit budget guard
      (see Settings.dev_live_serp_budget) so it is never reachable by
      accident during ordinary development.

    Default is `replay`, not `mock` — per the 'no live SerpAPI usage during
    development, but also no synthetic-only testing' directive: development
    work should exercise real historical measurements, not invented ones.
    """

    mock = "mock"
    replay = "replay"
    live = "live"


class LiveProviderBlockedError(RuntimeError):
    """Raised when EVALUATION_MODE=live but the live-provider budget guard
    blocks the call. Never caught to silently substitute mock/replay data —
    that would be exactly the silent fallback this exists to prevent. Callers
    that want a soft failure must catch this explicitly and record the
    provider as unavailable, the same way an unconfigured provider is
    already handled elsewhere in this codebase."""
