import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from sqlmodel import Session, select

from app.ai_visibility.surfaces import AI_VISIBILITY_SURFACES, AISurface
from app.ai_visibility.visibility_engine import run_ai_visibility_agent
from app.competitors.classification import classify_competitors_for_run
from app.competitors.discovery_engine import mine_ai_visibility_competitors
from app.competitors.market_map import compute_competitor_rankings
from app.core.config import Settings
from app.core.evaluation_mode import EvaluationMode
from app.core.storage import RawArtifactStore
from app.core.urls import normalize_hostname
from app.crawler.security import CrawlSecurityPolicy
from app.intent.intent_engine import run_intent_expansion_agent
from app.intent.quality import apply_quality_gate
from app.models.ai_visibility import AIVisibilityObservation, PromptFamily, PromptVariant
from app.models.competitor import Competitor
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.finding import Finding
from app.models.intent import Intent
from app.models.research import ResearchRun
from app.models.research_task import ResearchTask, TaskType
from app.models.serp import SerpObservation
from app.models.store import Store
from app.page_intelligence.gap_engine import _summarize_our_catalog, analyze_one_gap_candidate, build_gap_candidate
from app.providers.ai.router import ModelRouter
from app.providers.search.base import SearchProvider
from app.research.findings_engine import DOMINANT_COMPETITOR_MAX_AVG_RANK, DOMINANT_COMPETITOR_MIN_APPEARANCES
from app.research.finding_validation import record_evidence_check
from app.serp.serp_engine import run_serp_agent

QUERY_EXPANSION_MAX_INTENTS = 3


@dataclass
class TaskContext:
    """Shared handles every Executor worker needs — mirrors the constructor
    args ResearchOrchestrator already threads through the fixed pipeline
    steps, just packaged for the dispatch functions below."""

    session: Session
    router: ModelRouter
    storage: RawArtifactStore
    search_provider: SearchProvider
    settings: Settings
    store: Store
    run: ResearchRun
    agent_run_id: uuid.UUID | None


@dataclass
class TaskResult:
    evidence_ids: list[str] = field(default_factory=list)
    discovered_entities: dict = field(default_factory=dict)
    result_summary: str = ""
    cost: float | None = None
    # Reserved for future use — Group D2 V1 routes all new-task proposals
    # through the Research Planner (app/research/planner.py), not through
    # individual worker suggestions.
    follow_up_suggestions: list = field(default_factory=list)


async def execute_competitor_discovery_batch(ctx: TaskContext, task: ResearchTask) -> TaskResult:
    """Zero-cost seed task for the loop — mines ai_visibility_observations
    already collected by the fixed pipeline phases (Group D1). Part G-B5:
    the SERP half of discovery now runs earlier, right after the serp_batch
    fixed phase (see ResearchOrchestrator.execute_run,
    app.competitors.discovery_engine.mine_serp_competitors) — specifically
    so Competitor rows exist *before* ai_visibility_batch runs, letting
    detect_competitors_mentioned (app.ai_visibility.visibility_engine) match
    real domains in the AI's response text even on a store's first-ever run.
    Running it again here would duplicate every SERP relationship, since
    CompetitorRelationship rows are immutable/append-only. Part G-B2:
    classification runs immediately after, same task, no new agent_run/cost
    — every Competitor touched this run (including ones seeded by the
    earlier SERP step) is (re)classified so marketplaces/social/gov domains
    never get displayed as business competitors."""
    relationships = mine_ai_visibility_competitors(
        session=ctx.session,
        store_id=ctx.store.id,
        store_url=ctx.store.url,
        research_run_id=ctx.run.id,
    )
    unique_competitors = {r.competitor_id for r in relationships}
    classified_count = classify_competitors_for_run(ctx.session, ctx.store.id, ctx.run.id)

    summary = (
        f"اكتشفنا {len(unique_competitors)} منافس عبر {len(relationships)} إشارة/استشهاد AI"
        if relationships
        else "لم يُذكر أي منافس في محاولات AI هذا التشغيل"
    )
    return TaskResult(
        discovered_entities={
            "competitor_relationships": len(relationships),
            "unique_competitors": len(unique_competitors),
            "competitors_classified": classified_count,
        },
        result_summary=summary,
        cost=0.0,
    )


async def _execute_gap_task(ctx: TaskContext, task: ResearchTask) -> TaskResult:
    """Shared implementation for competitor_deep_dive and page_compare —
    both resolve to the same action in V1 (crawl the competitor's winning
    page for one specific intent, compare it against our catalog). They
    stay distinct TaskType values for tree readability (the Planner may
    propose either depending on what triggered the investigation), not
    because the execution differs."""
    competitor_id = task.input.get("competitor_id")
    intent_id = task.input.get("intent_id")
    if not competitor_id or not intent_id:
        return TaskResult(result_summary="مدخلات ناقصة: competitor_id أو intent_id مفقود")

    candidate = build_gap_candidate(ctx.session, ctx.run.id, uuid.UUID(intent_id), uuid.UUID(competitor_id))
    if candidate is None:
        return TaskResult(result_summary="تعذر تحديد صفحة المنافس الفائزة لهذه النية")

    our_catalog_summary = _summarize_our_catalog(ctx.session, ctx.store.id)
    crawl_policy = CrawlSecurityPolicy(
        max_response_bytes=ctx.settings.crawler_max_response_bytes,
        request_timeout_seconds=ctx.settings.crawler_request_timeout_seconds,
        user_agent=ctx.settings.crawler_user_agent,
    )

    analysis = await analyze_one_gap_candidate(
        session=ctx.session,
        router=ctx.router,
        storage=ctx.storage,
        store_id=ctx.store.id,
        research_run_id=ctx.run.id,
        agent_run_id=ctx.agent_run_id,
        candidate=candidate,
        our_catalog_summary=our_catalog_summary,
        crawl_policy=crawl_policy,
    )
    if analysis is None:
        return TaskResult(
            result_summary=f"تعذر زحف أو تحليل صفحة {candidate.competitor.domain}",
            discovered_entities={"pages_crawled": 0},
        )

    evidence = ctx.session.exec(
        select(Evidence)
        .where(Evidence.source_type == EvidenceSourceType.page_gap_analysis)
        .where(Evidence.source_id == analysis.id)
    ).first()

    return TaskResult(
        evidence_ids=[str(evidence.id)] if evidence else [],
        discovered_entities={"page_gap_analyses": 1, "gaps_found": len(analysis.gaps)},
        result_summary=f"وجدنا {len(analysis.gaps)} فجوة مقابل {candidate.competitor.domain}: {analysis.recommendation_summary}",
    )


async def execute_competitor_deep_dive(ctx: TaskContext, task: ResearchTask) -> TaskResult:
    return await _execute_gap_task(ctx, task)


async def execute_page_compare(ctx: TaskContext, task: ResearchTask) -> TaskResult:
    return await _execute_gap_task(ctx, task)


async def execute_query_expansion(ctx: TaskContext, task: ResearchTask) -> TaskResult:
    """Generates a small set of closely-related query variants anchored on
    one specific intent — reuses run_intent_expansion_agent unmodified,
    scoped via fallback_page_titles=[intent.topic] instead of the whole
    catalog, so it expands around that one topic only."""
    intent_id = task.input.get("intent_id")
    if not intent_id:
        return TaskResult(result_summary="مدخل ناقص: intent_id مفقود")

    intent = ctx.session.get(Intent, uuid.UUID(intent_id))
    if intent is None:
        return TaskResult(result_summary="النية غير موجودة")

    generated_intents = await run_intent_expansion_agent(
        session=ctx.session,
        router=ctx.router,
        store_id=ctx.store.id,
        research_run_id=ctx.run.id,
        agent_run_id=ctx.agent_run_id,
        categories=[],
        products=[],
        fallback_page_titles=[intent.topic],
        country=intent.country,
        language=intent.language,
        max_intents=QUERY_EXPANSION_MAX_INTENTS,
        already_generated=0,
    )
    # Same deterministic quality gate as the fixed intent_agent_run phase
    # (Part G-B1) — a follow-up expansion can drift into scraped-title
    # territory exactly like the original AI expansion can.
    new_intents = apply_quality_gate(ctx.session, generated_intents, ctx.store.id)

    summary = (
        f"وسّعنا نية '{intent.topic}' إلى {len(new_intents)} صياغة بحث إضافية"
        if new_intents
        else f"لم نجد صياغات بحث إضافية ذات قيمة لنية '{intent.topic}'"
    )
    return TaskResult(discovered_entities={"intents_generated": len(new_intents)}, result_summary=summary)


async def execute_validate_finding(ctx: TaskContext, task: ResearchTask) -> TaskResult:
    """The Validation Agent: re-checks a candidate Finding with one
    additional real signal (Part G-B3: recorded as a named, independent
    evidence source — 'google' for a fresh SERP requery, 'store' for the
    deterministic market-map fallback — never a blind confidence nudge).
    Re-checking the SAME source twice only refreshes that source's entry;
    validated status requires a SECOND, different source to also agree
    (see app.research.finding_validation)."""
    finding_id = task.input.get("finding_id")
    if not finding_id:
        return TaskResult(result_summary="مدخل ناقص: finding_id مفقود")

    finding = ctx.session.get(Finding, uuid.UUID(finding_id))
    if finding is None:
        return TaskResult(result_summary="الاستنتاج غير موجود")

    affected_domains = set()
    for competitor_id_str in finding.affected_competitors:
        competitor = ctx.session.get(Competitor, uuid.UUID(competitor_id_str))
        if competitor is not None:
            affected_domains.add(competitor.domain)

    source = "store"
    detail: str
    supports_finding: bool

    intent = None
    if finding.affected_intents:
        intent = ctx.session.get(Intent, uuid.UUID(finding.affected_intents[0]))

    if intent is not None:
        # Part H7 — idempotency: reuse this task's own prior observation
        # (if a re-dispatch is somehow re-executing it) instead of issuing
        # a second real query and a duplicate row.
        existing_observation = ctx.session.exec(
            select(SerpObservation).where(SerpObservation.origin_task_id == task.id)
        ).first()
        observations = (
            [existing_observation]
            if existing_observation is not None
            else await run_serp_agent(
                session=ctx.session,
                search_provider=ctx.search_provider,
                store_id=ctx.store.id,
                store_url=ctx.store.url,
                research_run_id=ctx.run.id,
                agent_run_id=ctx.agent_run_id,
                intents=[intent],
                country=intent.country,
                language=intent.language,
                num_results=ctx.settings.serp_num_results,
                max_queries=1,
                storage=ctx.storage,
            )
        )
        if observations:
            observation = observations[0]
            # Marks this as a Discovery-tier check, not part of the fixed
            # Control cadence (Group D2 design decision #2) — keeps
            # compute_visibility_metrics unaffected by this extra query.
            observation.origin_task_id = task.id
            ctx.session.add(observation)
            ctx.session.commit()
            source = "google"
            result_domains = {normalize_hostname(r.get("domain", "")) for r in observation.results[:3]}
            supports_finding = bool(affected_domains & result_domains)
            detail = "ظهر ضمن أفضل 3 نتائج في بحث Google جديد" if supports_finding else "لم يظهر في بحث Google جديد"
        else:
            supports_finding = False
            detail = "تعذر تنفيذ بحث Google إضافي"
    else:
        rankings = compute_competitor_rankings(ctx.session, ctx.run.id)
        supports_finding = any(
            r.domain in affected_domains
            and r.serp_appearances >= DOMINANT_COMPETITOR_MIN_APPEARANCES
            and (r.avg_serp_rank or 99) <= DOMINANT_COMPETITOR_MAX_AVG_RANK
            for r in rankings
        )
        detail = "لا يزال يستوفي شروط الهيمنة في خريطة السوق الحالية" if supports_finding else "لم يعد يستوفي شروط الهيمنة"

    record_evidence_check(finding, source=source, supports=supports_finding, detail=detail)
    ctx.session.add(finding)
    ctx.session.commit()
    ctx.session.refresh(finding)

    return TaskResult(
        discovered_entities={"validation_delta": 1 if supports_finding else 0},
        result_summary=f"تحقّق عبر {source}: الثقة الآن {finding.confidence:.2f} ({finding.status.value})",
    )


async def execute_search_google(ctx: TaskContext, task: ResearchTask) -> TaskResult:
    """Part F.5-10 — one extra, Planner-triggered Google check for a single
    intent (Discovery-tier, origin_task_id-tagged — Control cadence metrics
    stay unaffected). Same mechanism validate_finding already uses for its
    SERP leg, promoted to its own task type so the Planner can ask for it
    directly instead of only as a side-effect of finding validation."""
    intent_id = task.input.get("intent_id")
    if not intent_id:
        return TaskResult(result_summary="مدخل ناقص: intent_id مفقود")
    intent = ctx.session.get(Intent, uuid.UUID(intent_id))
    if intent is None:
        return TaskResult(result_summary="النية غير موجودة")

    # Part H7 — idempotency: if this exact task already produced an
    # observation (e.g. re-dispatched after a crash between commit and ack),
    # reuse it instead of issuing a second real query and a duplicate row.
    existing = ctx.session.exec(select(SerpObservation).where(SerpObservation.origin_task_id == task.id)).first()
    if existing is not None:
        return TaskResult(
            discovered_entities={"serp_observations": 0},
            result_summary=f"(مكرر، تم تجاهله) بحث Google إضافي لـ'{intent.topic}' نُفِّذ مسبقًا لهذه المهمة",
        )

    observations = await run_serp_agent(
        session=ctx.session, search_provider=ctx.search_provider, store_id=ctx.store.id, store_url=ctx.store.url,
        research_run_id=ctx.run.id, agent_run_id=ctx.agent_run_id, intents=[intent], country=intent.country,
        language=intent.language, num_results=ctx.settings.serp_num_results, max_queries=1, storage=ctx.storage,
    )
    if not observations:
        return TaskResult(result_summary=f"تعذر تنفيذ بحث Google إضافي لنية '{intent.topic}'")

    observation = observations[0]
    observation.origin_task_id = task.id
    ctx.session.add(observation)
    ctx.session.commit()
    summary = (
        f"بحث Google إضافي لـ'{intent.topic}': رتبة {observation.client_rank}"
        if observation.client_rank
        else f"بحث Google إضافي لـ'{intent.topic}': المتجر غير ظاهر"
    )
    return TaskResult(discovered_entities={"serp_observations": 1}, result_summary=summary)


async def _execute_ai_visibility_surface(ctx: TaskContext, task: ResearchTask, surface: AISurface) -> TaskResult:
    """Shared by the three per-surface task types below — one extra,
    Planner-triggered probe of a single already-generated prompt on one
    specific AI surface (Part F.5-10). Reuses whatever PromptVariant the
    fixed prompt_family_batch phase already generated for this intent
    this run; if none exists there's nothing meaningful to probe."""
    intent_id = task.input.get("intent_id")
    if not intent_id:
        return TaskResult(result_summary="مدخل ناقص: intent_id مفقود")
    intent = ctx.session.get(Intent, uuid.UUID(intent_id))
    if intent is None:
        return TaskResult(result_summary="النية غير موجودة")

    # In replay mode no provider call happens at all, so an unconfigured
    # provider key is irrelevant — only gate on it for a genuine live probe.
    if ctx.settings.evaluation_mode != EvaluationMode.replay and surface.provider not in ctx.router.configured_provider_names:
        return TaskResult(result_summary=f"سطح {surface.surface} غير مُفعَّل حاليًا (لا يوجد مفتاح API مهيّأ)")

    family = ctx.session.exec(select(PromptFamily).where(PromptFamily.intent_id == intent.id)).first()
    variant = (
        ctx.session.exec(select(PromptVariant).where(PromptVariant.prompt_family_id == family.id)).first()
        if family is not None
        else None
    )
    if variant is None:
        return TaskResult(result_summary=f"لا يوجد سؤال طبيعي مولَّد مسبقًا لنية '{intent.topic}' لفحصه على {surface.surface}")

    # Part H7 — idempotency: reuse this task's own prior observation(s) if
    # it is somehow re-dispatched, instead of issuing a second real probe
    # and a duplicate row.
    existing_observations = ctx.session.exec(
        select(AIVisibilityObservation).where(AIVisibilityObservation.origin_task_id == task.id)
    ).all()
    if existing_observations:
        return TaskResult(
            discovered_entities={"ai_visibility_observations": 0},
            result_summary=f"(مكرر، تم تجاهله) فحص {surface.surface} الإضافي لـ'{intent.topic}' نُفِّذ مسبقًا لهذه المهمة",
        )

    observations = await run_ai_visibility_agent(
        session=ctx.session, router=ctx.router, store_id=ctx.store.id, store_url=ctx.store.url,
        research_run_id=ctx.run.id, agent_run_id=ctx.agent_run_id, prompt_variants=[variant], surfaces=[surface],
        country=intent.country, language=intent.language, repetitions=1, storage=ctx.storage,
        evaluation_mode=ctx.settings.evaluation_mode,
    )
    if not observations:
        return TaskResult(result_summary=f"تعذر تنفيذ فحص {surface.surface} الإضافي لنية '{intent.topic}'")

    for observation in observations:
        observation.origin_task_id = task.id
    ctx.session.commit()

    mentioned = observations[0].mentioned
    summary = f"فحص {surface.surface} الإضافي لـ'{intent.topic}': " + ("مذكور" if mentioned else "غير مذكور")
    return TaskResult(discovered_entities={"ai_visibility_observations": len(observations)}, result_summary=summary)


def _surface_by_name(name: str) -> AISurface:
    return next(s for s in AI_VISIBILITY_SURFACES if s.surface == name)


async def execute_ai_visibility_chatgpt(ctx: TaskContext, task: ResearchTask) -> TaskResult:
    return await _execute_ai_visibility_surface(ctx, task, _surface_by_name("chatgpt"))


async def execute_ai_visibility_gemini(ctx: TaskContext, task: ResearchTask) -> TaskResult:
    return await _execute_ai_visibility_surface(ctx, task, _surface_by_name("gemini"))


async def execute_ai_visibility_claude(ctx: TaskContext, task: ResearchTask) -> TaskResult:
    return await _execute_ai_visibility_surface(ctx, task, _surface_by_name("claude"))


async def execute_validate_cross_surface_finding(ctx: TaskContext, task: ResearchTask) -> TaskResult:
    """Same confidence-step validation as execute_validate_finding, but the
    additional signal it checks is cross-surface (Part F.5-10 example: 'a
    competitor dominates Google here — do they also dominate ChatGPT/
    Gemini/Claude?') instead of one more SERP query."""
    finding_id = task.input.get("finding_id")
    if not finding_id:
        return TaskResult(result_summary="مدخل ناقص: finding_id مفقود")
    finding = ctx.session.get(Finding, uuid.UUID(finding_id))
    if finding is None:
        return TaskResult(result_summary="الاستنتاج غير موجود")

    affected_domains = set()
    for competitor_id_str in finding.affected_competitors:
        competitor = ctx.session.get(Competitor, uuid.UUID(competitor_id_str))
        if competitor is not None:
            affected_domains.add(competitor.domain)

    ai_observations = ctx.session.exec(
        select(AIVisibilityObservation).where(AIVisibilityObservation.research_run_id == ctx.run.id)
    ).all()
    cross_surface_mentions = sum(
        1 for o in ai_observations if any(domain in o.competitors_mentioned for domain in affected_domains)
    )
    supports_finding = cross_surface_mentions > 0
    detail = (
        f"ذُكر المنافس {cross_surface_mentions} مرة عبر أسطح AI" if supports_finding else "لم يُذكر المنافس على أي سطح AI"
    )

    # Part G-B3 — recorded as the "chatgpt" evidence source (today's only
    # configured AI surface — Part G-B4 keeps the Planner from proposing
    # this check when no AI surface is actually configured at all).
    record_evidence_check(finding, source="chatgpt", supports=supports_finding, detail=detail)
    ctx.session.add(finding)
    ctx.session.commit()
    ctx.session.refresh(finding)

    return TaskResult(
        discovered_entities={"cross_surface_mentions": cross_surface_mentions},
        result_summary=f"تحقّق عبر الأسطح: {cross_surface_mentions} إشارة على أسطح AI — الثقة الآن {finding.confidence:.2f} ({finding.status.value})",
    )


TASK_TYPE_WORKERS: dict[TaskType, Callable[[TaskContext, ResearchTask], Awaitable[TaskResult]]] = {
    TaskType.competitor_discovery_batch: execute_competitor_discovery_batch,
    TaskType.competitor_deep_dive: execute_competitor_deep_dive,
    TaskType.page_compare: execute_page_compare,
    TaskType.query_expansion: execute_query_expansion,
    TaskType.validate_finding: execute_validate_finding,
    TaskType.search_google: execute_search_google,
    TaskType.ai_visibility_chatgpt: execute_ai_visibility_chatgpt,
    TaskType.ai_visibility_gemini: execute_ai_visibility_gemini,
    TaskType.ai_visibility_claude: execute_ai_visibility_claude,
    TaskType.validate_cross_surface_finding: execute_validate_cross_surface_finding,
}
