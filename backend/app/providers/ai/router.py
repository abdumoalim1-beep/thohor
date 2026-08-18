import hashlib
import json
import uuid
from dataclasses import dataclass

from pydantic import BaseModel
from sqlmodel import Session, select

from app.models.ai_execution import AIExecution, AIExecutionStatus
from app.providers.ai.base import AIMessage, AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.pricing import estimate_cost_usd


@dataclass(frozen=True)
class ModelChoice:
    provider: str
    model: str


@dataclass(frozen=True)
class TaskRoute:
    primary: ModelChoice
    fallback: ModelChoice | None = None


# Capability-based routing: callers ask for a task_type, never a model name.
# Cheap/fast models handle classification-shaped work; reasoning-heavy tasks
# get a stronger model. Adjust freely — this is config, not code callers
# depend on.
DEFAULT_ROUTES: dict[str, TaskRoute] = {
    "classification": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    "entity_extraction": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    "page_type_detection": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    "intent_expansion": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    "prompt_family_generation": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    "page_gap_analysis": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    "page_rebuild_generation": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    "article_draft_generation": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    "winning_page_analysis": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    "research_planning": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    "ambiguous_store_understanding": TaskRoute(
        primary=ModelChoice("anthropic", "claude-sonnet-4-5-20250929"),
        fallback=ModelChoice("openai", "gpt-4o"),
    ),
    # Part R2-F1 — last-resort fallback only, called when
    # app.crawler.locale_detection's deterministic pass is inconclusive.
    # Same cheap/fast tier as classification; this is never the primary
    # locale signal.
    "locale_resolution": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    # No fallback on either of these two — a web-search identity/competitor
    # call must never silently fall back to a second provider making the
    # same claims up from its own training data instead of a real search.
    # Crawl data is the fallback for identity, never another AI call.
    "store_identity_resolution": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=None,
    ),
    "competitor_discovery_search": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=None,
    ),
    # Phase 5 — pure generation from already-known identity+competitors, no
    # web_search needed, same cheap/fast tier as the other generation tasks.
    "visibility_question_generation": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
    # Structured classification of an already-captured answer — no
    # web_search needed (it's analyzing text, not searching), same
    # cheap/fast generation tier as everything else.
    "answer_analysis": TaskRoute(
        primary=ModelChoice("openai", "gpt-4o-mini"),
        fallback=ModelChoice("anthropic", "claude-haiku-4-5-20251001"),
    ),
}


def _input_hash(task_type: str, model: str, prompt_version: str | None, messages: list[AIMessage]) -> str:
    payload = json.dumps([m.model_dump() for m in messages], sort_keys=True)
    raw = f"{task_type}|{model}|{prompt_version or ''}|{payload}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _strip_markdown_json_fence(text: str) -> str:
    """Models frequently wrap JSON output in a ```json ... ``` fence despite
    being told not to. Strip it rather than failing the whole call on a
    purely cosmetic formatting choice."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


class ModelRouter:
    """Capability-based AI dispatch.

    Callers request a task_type; the router picks provider/model, retries
    once on the primary, falls back to a secondary provider on failure, logs
    every attempt to ai_executions (the usage/cost ledger), and skips
    re-paying for a call already made with identical task_type/model/
    prompt_version/input.
    """

    def __init__(self, providers: dict[str, AIProvider], routes: dict[str, TaskRoute] | None = None):
        self._providers = providers
        self._routes = routes or DEFAULT_ROUTES

    @property
    def configured_provider_names(self) -> list[str]:
        """Providers actually available (real key present, or 'mock' in
        tests) — used by the AI Visibility Test Matrix to only probe
        engines that are actually usable, mirroring build_providers()'s
        'no key, simply absent' behavior."""
        return [name for name in self._providers if name != "mock"]

    def _provider_for(self, name: str) -> AIProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise RuntimeError(f"AI provider '{name}' is not configured (missing API key?)")
        return provider

    async def execute(
        self,
        *,
        session: Session,
        task_type: str,
        messages: list[AIMessage],
        research_run_id: uuid.UUID | None = None,
        agent_run_id: uuid.UUID | None = None,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
        schema_version: str | None = None,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        use_cache: bool = True,
        enable_web_search: bool = False,
    ) -> AIResponse:
        route = self._routes.get(task_type)
        if route is None:
            raise ValueError(f"No route configured for task_type='{task_type}'")

        input_hash = _input_hash(task_type, route.primary.model, prompt_version, messages)

        if use_cache:
            cached = self._find_cached(session, task_type, route.primary.model, prompt_version, input_hash)
            if cached is not None:
                return AIResponse(
                    provider=cached.provider,
                    model=cached.model,
                    text="",
                    parsed=cached.parsed_output,
                    usage=AIUsage(input_tokens=cached.input_tokens or 0, output_tokens=cached.output_tokens or 0),
                    latency_ms=0,
                    execution_id=cached.id,
                )

        attempts = [route.primary] + ([route.fallback] if route.fallback else [])
        last_error: Exception | None = None

        for attempt_no, choice in enumerate(attempts):
            try:
                provider = self._provider_for(choice.provider)
            except RuntimeError as exc:
                last_error = exc
                continue

            request = AIRequest(
                task_type=task_type,
                model=choice.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                enable_web_search=enable_web_search,
            )
            try:
                response = await provider.generate(request)
                parsed = self._parse(response.text, response_schema)
                cost = estimate_cost_usd(
                    choice.provider, choice.model, response.usage.input_tokens, response.usage.output_tokens
                )
                status = AIExecutionStatus.success if attempt_no == 0 else AIExecutionStatus.fallback
                execution = self._log(
                    session=session,
                    research_run_id=research_run_id,
                    agent_run_id=agent_run_id,
                    provider=choice.provider,
                    model=choice.model,
                    task_type=task_type,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                    input_hash=input_hash,
                    parsed_output=parsed,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    cost_usd=cost,
                    latency_ms=response.latency_ms,
                    status=status,
                    error=None,
                )
                response.parsed = parsed
                response.execution_id = execution.id
                return response
            except Exception as exc:  # noqa: BLE001 — any attempt may fail; the loop is the fallback mechanism
                last_error = exc
                self._log(
                    session=session,
                    research_run_id=research_run_id,
                    agent_run_id=agent_run_id,
                    provider=choice.provider,
                    model=choice.model,
                    task_type=task_type,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                    input_hash=input_hash,
                    parsed_output=None,
                    input_tokens=None,
                    output_tokens=None,
                    cost_usd=None,
                    latency_ms=None,
                    status=AIExecutionStatus.error,
                    error=str(exc),
                )
                continue

        raise RuntimeError(f"All providers failed for task_type='{task_type}'") from last_error

    async def execute_single(
        self,
        *,
        session: Session,
        provider_name: str,
        model: str,
        task_type: str,
        messages: list[AIMessage],
        research_run_id: uuid.UUID | None = None,
        agent_run_id: uuid.UUID | None = None,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
        schema_version: str | None = None,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        enable_web_search: bool = False,
    ) -> AIResponse:
        """Calls exactly the specified provider/model once — no routing, no
        fallback, no caching. For the AI Visibility Test Matrix, where the
        point is comparing specific engines against each other, not picking
        whichever one succeeds first. Every call still logs to
        ai_executions like execute() does.
        """
        provider = self._provider_for(provider_name)
        request = AIRequest(
            task_type=task_type,
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            enable_web_search=enable_web_search,
        )

        input_hash = _input_hash(task_type, model, prompt_version, messages)

        try:
            response = await provider.generate(request)
        except Exception as exc:  # noqa: BLE001 — normalized into a logged error row, no fallback to try
            self._log(
                session=session,
                research_run_id=research_run_id,
                agent_run_id=agent_run_id,
                provider=provider_name,
                model=model,
                task_type=task_type,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                schema_version=schema_version,
                input_hash=input_hash,
                parsed_output=None,
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
                latency_ms=None,
                status=AIExecutionStatus.error,
                error=str(exc),
            )
            raise

        parsed = self._parse(response.text, response_schema)
        cost = estimate_cost_usd(provider_name, model, response.usage.input_tokens, response.usage.output_tokens)
        execution = self._log(
            session=session,
            research_run_id=research_run_id,
            agent_run_id=agent_run_id,
            provider=provider_name,
            model=model,
            task_type=task_type,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            schema_version=schema_version,
            input_hash=input_hash,
            parsed_output=parsed,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=cost,
            latency_ms=response.latency_ms,
            status=AIExecutionStatus.success,
            error=None,
        )
        response.parsed = parsed
        response.execution_id = execution.id
        return response

    @staticmethod
    def _parse(text: str, schema: type[BaseModel] | None) -> dict | None:
        if schema is None:
            return None
        data = json.loads(_strip_markdown_json_fence(text))
        return schema.model_validate(data).model_dump(mode="json")

    @staticmethod
    def _find_cached(
        session: Session, task_type: str, model: str, prompt_version: str | None, input_hash: str
    ) -> AIExecution | None:
        statement = (
            select(AIExecution)
            .where(AIExecution.task_type == task_type)
            .where(AIExecution.model == model)
            .where(AIExecution.prompt_version == prompt_version)
            .where(AIExecution.input_hash == input_hash)
            .where(AIExecution.status == AIExecutionStatus.success)
            .order_by(AIExecution.created_at.desc())  # type: ignore[arg-type]
        )
        return session.exec(statement).first()

    @staticmethod
    def _log(*, session: Session, **kwargs) -> AIExecution:
        execution = AIExecution(**kwargs)
        session.add(execution)
        session.commit()
        session.refresh(execution)
        return execution
