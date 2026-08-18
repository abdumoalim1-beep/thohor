import uuid

from sqlmodel import Session, select

from app.competitors.market_map import compute_competitor_rankings
from app.models.finding import Finding
from app.models.intent import Intent
from app.models.research_task import ResearchTask
from app.prompts.research_planning import RESEARCH_PLANNING_PROMPT
from app.providers.ai.router import ModelRouter
from app.research.budget import ResearchBudget
from app.research.capabilities import ResearchCapabilities
from app.schemas.research_planning import NewTaskSuggestion, ResearchPlanResult

_TASK_TYPE_ARABIC_LABEL: dict[str, str] = {
    "ai_visibility_chatgpt": "فحص ظهور إضافي على ChatGPT (ai_visibility_chatgpt)",
    "ai_visibility_gemini": "فحص ظهور إضافي على Gemini (ai_visibility_gemini)",
    "ai_visibility_claude": "فحص ظهور إضافي على Claude (ai_visibility_claude)",
    "validate_cross_surface_finding": "التحقق عبر أسطح AI متعددة (validate_cross_surface_finding)",
}


def _unavailable_task_types_notice(capabilities: ResearchCapabilities) -> str:
    unavailable = capabilities.unavailable_task_types()
    if not unavailable:
        return "(كل أنواع المهام متاحة حاليًا)"
    lines = [f"- {_TASK_TYPE_ARABIC_LABEL.get(t.value, t.value)}" for t in sorted(unavailable, key=lambda t: t.value)]
    return "\n".join(lines)


def _summarize_market_map(session: Session, research_run_id: uuid.UUID, limit: int = 10) -> str:
    rankings = compute_competitor_rankings(session, research_run_id)
    lines = [
        f"- {r.domain} ({r.competitor_type.value}): serp_appearances={r.serp_appearances}, "
        f"avg_serp_rank={r.avg_serp_rank}, ai_citation_count={r.ai_citation_count}"
        for r in rankings[:limit]
    ]
    return "\n".join(lines) or "(لا يوجد منافسون مكتشفون بعد)"


def _summarize_intents(session: Session, research_run_id: uuid.UUID, limit: int = 15) -> str:
    intents = session.exec(
        select(Intent)
        .where(Intent.research_run_id == research_run_id)
        .order_by(Intent.confidence.desc())  # type: ignore[arg-type]
    ).all()
    lines = [f"- [id={i.id}] {i.topic} (confidence={i.confidence:.2f})" for i in intents[:limit]]
    return "\n".join(lines) or "(لا توجد نوايا بعد)"


def _summarize_findings(session: Session, research_run_id: uuid.UUID, limit: int = 10) -> str:
    findings = session.exec(select(Finding).where(Finding.research_run_id == research_run_id)).all()
    lines = [
        f"- [id={f.id}] [{f.status.value}] {f.statement} (confidence={f.confidence:.2f})" for f in findings[:limit]
    ]
    return "\n".join(lines) or "(لا توجد استنتاجات بعد)"


def _summarize_prior_tasks(session: Session, research_run_id: uuid.UUID, limit: int = 30) -> str:
    tasks = session.exec(
        select(ResearchTask)
        .where(ResearchTask.research_run_id == research_run_id)
        .order_by(ResearchTask.created_at.desc())  # type: ignore[arg-type]
    ).all()
    lines = [
        f"- [{t.task_type.value}] {t.reason or ''} -> {t.result_summary or '(بلا نتيجة بعد)'}" for t in tasks[:limit]
    ]
    return "\n".join(lines) or "(لا توجد مهام سابقة)"


async def plan_next_tasks(
    *,
    session: Session,
    router: ModelRouter,
    research_run_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    store_id: uuid.UUID,
    budget: ResearchBudget,
    capabilities: ResearchCapabilities,
) -> list[NewTaskSuggestion]:
    """Looks at current state (market map, findings, prior tasks) and
    proposes what to research next as structured suggestions — never
    executes or writes anything itself. The Orchestrator decides whether to
    accept each suggestion (budget, dedup, depth rules) — Group D2 design
    decision #4.

    Part G-B4: `capabilities` tells the prompt which task types have no
    underlying provider configured this run, so it stops proposing
    ai_visibility_gemini/ai_visibility_claude etc. when there's no key —
    and the returned list is filtered against the same capabilities as a
    second, deterministic guarantee in case the model ignores the
    instruction."""
    market_map_summary = _summarize_market_map(session, research_run_id)
    intents_summary = _summarize_intents(session, research_run_id)
    findings_summary = _summarize_findings(session, research_run_id)
    prior_tasks_summary = _summarize_prior_tasks(session, research_run_id)
    remaining_tasks_budget = max(budget.max_tasks - budget.tasks_used, 0)
    unavailable_task_types_notice = _unavailable_task_types_notice(capabilities)

    messages = RESEARCH_PLANNING_PROMPT.render(
        market_map_summary=market_map_summary,
        intents_summary=intents_summary,
        findings_summary=findings_summary,
        prior_tasks_summary=prior_tasks_summary,
        remaining_tasks_budget=str(remaining_tasks_budget),
        unavailable_task_types_notice=unavailable_task_types_notice,
    )

    response = await router.execute(
        session=session,
        task_type="research_planning",
        messages=messages,
        research_run_id=research_run_id,
        agent_run_id=agent_run_id,
        prompt_name=RESEARCH_PLANNING_PROMPT.name,
        prompt_version=RESEARCH_PLANNING_PROMPT.version,
        schema_version=RESEARCH_PLANNING_PROMPT.schema_version,
        response_schema=ResearchPlanResult,
    )

    if response.parsed is None:
        return []

    result = ResearchPlanResult.model_validate(response.parsed)
    return [s for s in result.new_tasks if capabilities.is_task_type_available(s.task_type)]
