from typing import Any
from urllib.parse import urlparse

from sqlmodel import Session

from app.core.config import Settings
from app.crawler.subprocess_fetch import fetch_and_extract_in_subprocess
from app.models.ai_execution import AIExecution
from app.models.recommendation import Recommendation, RecommendationHistory
from app.models.research import AgentRun, ResearchRun, RunStatus
from app.models.serp import SerpExecution, SerpExecutionStatus
from app.models.store import Store
from app.models.base import utcnow
from app.opportunities.on_demand_execution import generate_on_demand_implementation
from app.page_intelligence.on_demand_page_analysis import public_page_facts, winning_page_messages
from app.providers.search.base import SearchProvider, SearchRequest
from app.providers.search.pricing import estimate_search_cost_usd
from app.research.market_exploration import classify_result_domain, exploration_queries
from app.schemas.market_exploration import MarketExplorationResultItem
from app.schemas.winning_page_analysis import WinningPageAnalysisOutput


def mark_running(session: Session, run: ResearchRun, agent: AgentRun) -> None:
    now = utcnow()
    run.status = RunStatus.running
    run.started_at = run.started_at or now
    agent.status = RunStatus.running
    agent.started_at = agent.started_at or now
    session.add(run); session.add(agent); session.commit()


def mark_failed(session: Session, run: ResearchRun, agent: AgentRun, exc: Exception) -> None:
    now = utcnow()
    run.status = RunStatus.failed; run.error = str(exc); run.completed_at = now
    agent.status = RunStatus.failed; agent.error = str(exc); agent.completed_at = now
    session.add(run); session.add(agent); session.commit()


async def execute_market_exploration(
    session: Session, store: Store, run: ResearchRun, agent: AgentRun,
    topic: str, max_queries: int, provider: SearchProvider, settings: Settings,
) -> None:
    mark_running(session, run, agent)
    queries = exploration_queries(session, store, topic, max_queries)
    results: list[MarketExplorationResultItem] = []
    client_ranks: dict[str, int | None] = {}
    warnings: list[str] = []
    actual_cost = 0.0
    for query in queries:
        try:
            response = await provider.search(SearchRequest(
                keyword=query, country=store.country or settings.serp_default_country,
                language=store.language or settings.serp_default_language,
                num_results=settings.serp_num_results,
            ))
            cost = estimate_search_cost_usd(provider.underlying_provider_name)
            actual_cost += cost
            session.add(SerpExecution(
                research_run_id=run.id, agent_run_id=agent.id, provider=provider.underlying_provider_name,
                keyword=query, country=store.country or settings.serp_default_country,
                language=store.language or settings.serp_default_language, cost_usd=cost,
                latency_ms=response.latency_ms, status=SerpExecutionStatus.success,
            ))
            client_rank = None
            for item in response.results:
                entity_type = classify_result_domain(session, store, item.domain)
                if entity_type == "store" and client_rank is None:
                    client_rank = item.rank
                results.append(MarketExplorationResultItem(
                    query=query, rank=item.rank, domain=item.domain, url=item.url,
                    title=item.title, entity_type=entity_type,
                ))
            client_ranks[query] = client_rank
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"تعذر البحث عن '{query}': {exc}")
            session.add(SerpExecution(
                research_run_id=run.id, agent_run_id=agent.id, provider=provider.underlying_provider_name,
                keyword=query, country=store.country or settings.serp_default_country,
                language=store.language or settings.serp_default_language,
                status=SerpExecutionStatus.error, error=str(exc),
            ))
    domain_counts: dict[str, int] = {}
    for item in results:
        if item.entity_type != "store":
            domain_counts[item.domain] = domain_counts.get(item.domain, 0) + 1
    recurring = [{"domain": domain, "appearances": count} for domain, count in sorted(domain_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:10]]
    now = utcnow()
    agent.status = RunStatus.completed; agent.completed_at = now; agent.warnings = warnings
    agent.findings = {"topic": topic, "queries": queries, "results": [item.model_dump() for item in results], "client_ranks": client_ranks, "recurring_domains": recurring, "actual_serp_cost_usd": actual_cost}
    run.status = RunStatus.completed; run.completed_at = now
    session.add(agent); session.add(run); session.commit()


async def execute_winning_page_analysis(
    session: Session, store: Store, run: ResearchRun, agent: AgentRun,
    request: dict, router: Any, settings: Settings,
) -> None:
    mark_running(session, run, agent)
    competitor_url = request["competitor_url"]
    competitor_page = await fetch_and_extract_in_subprocess(
        competitor_url, urlparse(competitor_url).hostname, settings.crawler_user_agent,
        settings.crawler_request_timeout_seconds, settings.crawler_max_response_bytes,
    )
    target_page = None
    if request.get("target_url"):
        target_url = request["target_url"]
        target_page = await fetch_and_extract_in_subprocess(
            target_url, urlparse(target_url).hostname, settings.crawler_user_agent,
            settings.crawler_request_timeout_seconds, settings.crawler_max_response_bytes,
        )
    response = await router.execute(
        session=session, task_type="winning_page_analysis",
        messages=winning_page_messages(request["query"], competitor_page.facts, target_page.facts if target_page else None),
        research_run_id=run.id, agent_run_id=agent.id, prompt_name="winning_page_analysis",
        prompt_version="v2", schema_version="v1", response_schema=WinningPageAnalysisOutput,
        max_tokens=3000, temperature=0.1,
    )
    if response.parsed is None or response.execution_id is None:
        raise RuntimeError("winning page analysis returned no persisted output")
    output = WinningPageAnalysisOutput.model_validate(response.parsed)
    now = utcnow()
    agent.status = RunStatus.completed; agent.completed_at = now
    agent.findings = {**request, "competitor_facts": public_page_facts(competitor_page.facts), "target_facts": public_page_facts(target_page.facts) if target_page else None, "analysis": output.model_dump(mode="json"), "ai_execution_id": str(response.execution_id)}
    run.status = RunStatus.completed; run.completed_at = now
    session.add(agent); session.add(run); session.commit()


async def execute_implementation_generation(
    session: Session, recommendation: Recommendation, run: ResearchRun, agent: AgentRun,
    mode: str, router: Any,
) -> None:
    mark_running(session, run, agent)
    output, execution_id = await generate_on_demand_implementation(session, router, recommendation, mode, run.id)
    package = dict(recommendation.implementation_package or {})
    generated = dict(package.get("on_demand") or {})
    generated[mode] = output.model_dump(mode="json")
    package["on_demand"] = generated
    recommendation.implementation_package = package; recommendation.updated_at = utcnow()
    session.add(recommendation)
    session.add(RecommendationHistory(recommendation_id=recommendation.id, research_run_id=run.id, event_type="implementation_generated", snapshot={"mode": mode, "ai_execution_id": str(execution_id)}))
    execution = session.get(AIExecution, execution_id)
    now = utcnow()
    agent.status = RunStatus.completed; agent.completed_at = now
    agent.findings = {"recommendation_id": str(recommendation.id), "mode": mode, "result": {"mode": mode, "status": "completed", "output": output.model_dump(mode="json"), "ai_execution_id": str(execution_id), "cost_usd": execution.cost_usd if execution else None}}
    run.status = RunStatus.completed; run.completed_at = now
    session.add(agent); session.add(run); session.commit()
