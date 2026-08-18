from dataclasses import dataclass

from app.ai_visibility.surfaces import resolve_configured_surfaces
from app.core.config import Settings
from app.models.research_task import TaskType
from app.providers.ai.router import ModelRouter

# Which AI-visibility task type each surface backs — used to compute which
# task types are actually runnable this run, never a static list (Part G-B4).
_SURFACE_TASK_TYPES: dict[str, TaskType] = {
    "chatgpt": TaskType.ai_visibility_chatgpt,
    "gemini": TaskType.ai_visibility_gemini,
    "claude": TaskType.ai_visibility_claude,
}


@dataclass(frozen=True)
class ResearchCapabilities:
    """What the Planner may propose and the Executor can actually run this
    run. Before Part G-B4 the Planner's prompt hardcoded all three AI
    surfaces as always-proposable, so it routinely suggested
    ai_visibility_gemini/ai_visibility_claude with no Google/Anthropic key
    configured — the Executor's `_execute_ai_visibility_surface` already
    caught this and returned a no-op ('غير مُفعَّل حاليًا'), but only after
    burning a task-budget slot and a research_task row with zero research
    value. This makes 'what's actually configured' an explicit object the
    Planner and the loop's acceptance logic both consult, instead of relying
    on every worker to defensively no-op."""

    configured_ai_surfaces: frozenset[str]
    search_configured: bool

    @property
    def any_ai_surface_configured(self) -> bool:
        return bool(self.configured_ai_surfaces)

    def unavailable_task_types(self) -> frozenset[TaskType]:
        """Discovery task types the Planner must not propose and the loop
        must not accept right now."""
        unavailable = {
            task_type
            for surface, task_type in _SURFACE_TASK_TYPES.items()
            if surface not in self.configured_ai_surfaces
        }
        if not self.any_ai_surface_configured:
            # validate_cross_surface_finding always records its evidence
            # under source="chatgpt" today (Part G-B3) — meaningless with no
            # AI surface configured at all.
            unavailable.add(TaskType.validate_cross_surface_finding)
        return frozenset(unavailable)

    def is_task_type_available(self, task_type: TaskType) -> bool:
        return task_type not in self.unavailable_task_types()


def resolve_research_capabilities(router: ModelRouter, settings: Settings) -> ResearchCapabilities:
    configured_surfaces = frozenset(s.surface for s in resolve_configured_surfaces(router))
    return ResearchCapabilities(
        configured_ai_surfaces=configured_surfaces,
        search_configured=bool(settings.serpapi_api_key),
    )
