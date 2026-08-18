import dataclasses

from sqlmodel import Session, func, select, update

from app.ai_visibility.prompt_family_engine import (
    run_prompt_family_agent,
    select_top_intents,
)
from app.ai_visibility.visibility_engine import (
    resolve_configured_engines,
    run_ai_visibility_agent,
)
from app.alerts.alert_engine import generate_alerts
from app.analysis.snapshots import update_component_snapshot
from app.ai_visibility.question_generation import generate_visibility_questions
from app.competitors.discovery_engine import mine_serp_competitors
from app.competitors.identity_discovery import discover_competitors
from app.core.cadence import compute_next_scheduled_run_at
from app.core.config import Settings
from app.core.storage import RawArtifactStore
from app.crawler.store_intelligence import (
    MIN_OBSERVATIONS_FOR_CLASSIFICATION,
    has_sufficient_observations_for_classification,
    run_crawl_agent,
    run_store_classification_agent,
    summarize_observations_for_context,
)
from app.intent.clustering import cluster_intents
from app.intent.intent_engine import (
    generate_deterministic_seed_intents,
    run_intent_expansion_agent,
)
from app.intent.quality import apply_quality_gate
from app.measurement.monitoring_engine import run_monitoring_pass
from app.models.base import utcnow
from app.models.catalog import Category, Product
from app.models.competitor import Competitor
from app.models.observation import PageObservation
from app.models.research import AgentRun, ResearchRun, ResearchRunType, RunStatus
from app.models.store import Store, StoreStatus
from app.opportunities.freshness import select_primary_recommendations
from app.store_intelligence.identity_resolver import persist_store_identity_fields, resolve_store_identity
from app.opportunities.quality_gate import check_recommendation_batch_quality
from app.opportunities.recommendation_engine import (
    run_opportunity_discovery_agent,
    run_recommendation_engine,
)
from app.providers.ai.router import ModelRouter
from app.providers.search.base import SearchProvider
from app.research.cancellation import CANCELLATION_STOP_REASON
from app.research.findings_engine import backfill_task_opportunity_impact
from app.research.loop import run_iterative_research_loop
from app.serp.serp_engine import run_serp_agent


def _start_agent_run(session: Session, research_run_id, agent_type: str) -> AgentRun:
    agent_run = AgentRun(research_run_id=research_run_id, agent_type=agent_type, status=RunStatus.running, started_at=utcnow())
    session.add(agent_run)
    session.commit()
    session.refresh(agent_run)
    return agent_run


def _complete_agent_run(session: Session, agent_run: AgentRun, *, findings: dict | None, evidence_ids: list | None = None) -> None:
    agent_run.status = RunStatus.completed
    agent_run.completed_at = utcnow()
    agent_run.findings = findings
    agent_run.evidence_ids = evidence_ids or []
    session.add(agent_run)
    session.commit()


def _fail_agent_run(session: Session, agent_run: AgentRun, error: str) -> None:
    agent_run.status = RunStatus.failed
    agent_run.completed_at = utcnow()
    agent_run.error = error
    session.add(agent_run)
    session.commit()


class ResearchOrchestrator:
    """Owns research_run sequencing/dependency logic. Deliberately framework-
    free — Celery tasks in app/workers/tasks.py call into this and do
    nothing else, so the execution layer (Celery today, potentially Temporal
    later) can be swapped without touching this class.
    """

    def __init__(
        self,
        *,
        session: Session,
        storage: RawArtifactStore,
        router: ModelRouter,
        search_provider: SearchProvider,
        settings: Settings,
    ):
        self._session = session
        self._storage = storage
        self._router = router
        self._search_provider = search_provider
        self._settings = settings

    @staticmethod
    def create_pending_run(session: Session, store: Store, run_type: ResearchRunType = ResearchRunType.baseline) -> ResearchRun:
        """Cheap, synchronous: creates the research_run row the API returns
        immediately. Execution (execute_run) happens later, in the Celery
        worker, against this same row — never a second one."""
        run = ResearchRun(store_id=store.id, run_type=run_type, status=RunStatus.pending)
        session.add(run)
        session.commit()
        session.refresh(run)
        for component in ("basic", "google", "ai", "competitors", "opportunities"):
            update_component_snapshot(
                session, store_id=store.id, research_run_id=run.id,
                component=component, status="queued",
            )
        return run

    async def execute_run(self, store: Store, run: ResearchRun) -> ResearchRun:
        session = self._session

        # Part H7 — atomic claim: a research_run must execute its pipeline
        # exactly once, even if the same (store_id, research_run_id) is
        # dispatched twice (Celery at-least-once redelivery, an accidental
        # double .delay(), or a retried multi-store batch). The UPDATE's
        # WHERE clause only matches while status is still 'pending'; the
        # database resolves the race between concurrent claimants (whichever
        # UPDATE commits first wins the row), so at most one process ever
        # sees rowcount == 1 and proceeds past this point. Every other
        # caller sees rowcount == 0 and returns the run as-is — no crawl,
        # no observations, no agent_runs, nothing re-executed or duplicated.
        claim = session.execute(
            update(ResearchRun)
            .where(ResearchRun.id == run.id)
            .where(ResearchRun.status == RunStatus.pending)
            .values(status=RunStatus.running, started_at=utcnow(), evaluation_mode=self._settings.evaluation_mode.value)
        )
        session.commit()
        session.refresh(run)
        if claim.rowcount == 0:
            return run

        update_component_snapshot(
            session, store_id=store.id, research_run_id=run.id,
            component="basic", status="running",
        )

        crawl_agent_run = _start_agent_run(session, run.id, "crawl_agent_run")
        store.catalog_status = "scanning"
        session.add(store)
        session.commit()
        crawl_diagnostics: dict = {}
        try:
            observations = await run_crawl_agent(
                session=session,
                storage=self._storage,
                store_id=store.id,
                research_run_id=run.id,
                agent_run_id=crawl_agent_run.id,
                base_url=store.url,
                max_pages=(
                    self._settings.crawler_fast_max_pages
                    if run.run_type == ResearchRunType.baseline
                    else self._settings.crawler_max_pages_per_run
                ),
                max_depth=self._settings.crawler_max_depth,
                request_timeout_seconds=self._settings.crawler_request_timeout_seconds,
                max_response_bytes=self._settings.crawler_max_response_bytes,
                user_agent=self._settings.crawler_user_agent,
                router=self._router,
                max_concurrency=(self._settings.crawler_fast_concurrency if run.run_type == ResearchRunType.baseline else 2),
                overall_timeout_seconds=(
                    self._settings.crawler_fast_timeout_seconds if run.run_type == ResearchRunType.baseline else None
                ),
                stop_when_sufficient=run.run_type == ResearchRunType.baseline,
                min_pages_for_sufficiency=self._settings.crawler_fast_min_pages,
                max_playwright_fallbacks=self._settings.crawler_playwright_max_fallbacks,
                diagnostics=crawl_diagnostics,
            )
        except Exception as exc:  # noqa: BLE001 — a crawl failure ends the run; nothing downstream can proceed
            session.rollback()  # a failed flush leaves the session unusable until rolled back
            _fail_agent_run(session, crawl_agent_run, str(exc))
            store.catalog_status = "failed"
            session.add(store)
            run.status = RunStatus.failed
            run.completed_at = utcnow()
            run.error = f"crawl_agent_run failed: {exc}"
            session.add(run)
            session.commit()
            update_component_snapshot(
                session, store_id=store.id, research_run_id=run.id,
                component="basic", status="failed", error=str(exc),
            )
            return run

        # Distinguishes "the site actively blocked us" from "the site
        # genuinely has little content" — both look identical as a bare
        # observation count, but the user needs to be told which one
        # actually happened (spec: never silently treat a block as
        # success). "partial" only applies to a real, honest budget cap —
        # not blocking — kept separate from "blocked" deliberately.
        store.catalog_pages_crawled = len(observations)
        store.catalog_products_found = session.exec(
            select(func.count()).select_from(Product).where(Product.store_id == store.id)
        ).one()
        if crawl_diagnostics.get("blocked_detected") and store.catalog_products_found == 0:
            store.catalog_status = "blocked"
        elif len(observations) >= (
            self._settings.crawler_fast_max_pages if run.run_type == ResearchRunType.baseline
            else self._settings.crawler_max_pages_per_run
        ):
            store.catalog_status = "partial"
        else:
            store.catalog_status = "ready"
        store.last_catalog_scan_at = utcnow()
        session.add(store)
        session.commit()

        # Part R2-F1 — run_crawl_agent already resolved+persisted
        # store.country/language/locale_status; surface that resolution
        # (or explicit non-resolution) on the agent_run itself so it's
        # never a silent fact buried only in the stores table.
        _complete_agent_run(
            session,
            crawl_agent_run,
            findings={
                "pages_crawled": len(observations),
                "locale_status": store.locale_status,
                "locale_country": store.country,
                "locale_language": store.language,
                "locale_confidence": store.locale_confidence,
                "locale_source": store.locale_source,
            },
        )

        # Identity resolution — independent of crawl completeness. This is
        # the actual decoupling: a blocked/thin crawl no longer means the
        # store's name and activity are unknowable, since this asks the
        # web directly instead of relying only on what the crawler read.
        # Only for baseline runs — identity is a once-per-store concept,
        # not something a weekly monitoring run needs to re-resolve.
        identity = None
        if run.run_type == ResearchRunType.baseline:
            identity_agent_run = _start_agent_run(session, run.id, "store_identity_agent_run")
            try:
                crawl_context = summarize_observations_for_context(observations) if observations else None
                identity, identity_evidence_id = await resolve_store_identity(
                    session=session,
                    router=self._router,
                    store_id=store.id,
                    research_run_id=run.id,
                    agent_run_id=identity_agent_run.id,
                    store_url=store.url,
                    crawl_context=crawl_context,
                )
            except Exception as exc:  # noqa: BLE001 — identity resolution failing must never block the run
                session.rollback()
                _fail_agent_run(session, identity_agent_run, str(exc))
                identity = None
            else:
                if identity is not None:
                    _complete_agent_run(
                        session,
                        identity_agent_run,
                        findings=identity.model_dump(),
                        evidence_ids=[str(identity_evidence_id)] if identity_evidence_id else [],
                    )
                    persist_store_identity_fields(store, identity, source="web_search")
                    session.add(store)
                    session.commit()
                else:
                    # Crawl data (classification, below) becomes the fallback
                    # identity source — never the other way around.
                    _complete_agent_run(
                        session,
                        identity_agent_run,
                        findings={"skipped": True, "reason": "web_search_unavailable_or_failed"},
                        evidence_ids=[],
                    )

        # Identity-based competitor discovery — Phase 4, additive to (not a
        # replacement for) mine_serp_competitors/mine_ai_visibility_competitors
        # later in the pipeline. Only runs when identity resolution actually
        # produced something to search around; a store with no resolvable
        # identity has nothing meaningful to discover competitors from yet.
        discovered_competitors: list[Competitor] = []
        if run.run_type == ResearchRunType.baseline and identity is not None:
            competitor_discovery_agent_run = _start_agent_run(session, run.id, "identity_competitor_discovery_agent_run")
            try:
                discovered_competitors, discovery_evidence_ids = await discover_competitors(
                    session=session,
                    router=self._router,
                    store_id=store.id,
                    research_run_id=run.id,
                    agent_run_id=competitor_discovery_agent_run.id,
                    store_url=store.url,
                    identity=identity,
                    max_suggestions=self._settings.competitor_discovery_max_suggestions,
                )
            except Exception as exc:  # noqa: BLE001 — competitor suggestion failing must never block the run
                session.rollback()
                _fail_agent_run(session, competitor_discovery_agent_run, str(exc))
                store.competitor_discovery_status = "failed"
            else:
                _complete_agent_run(
                    session,
                    competitor_discovery_agent_run,
                    findings={"competitors_suggested": len(discovered_competitors)},
                    evidence_ids=[str(e) for e in discovery_evidence_ids],
                )
                store.competitor_discovery_status = "ready"
            store.last_competitor_scan_at = utcnow()
            session.add(store)
            session.commit()

        # Question generation — Phase 5, grounded in the same identity +
        # whatever competitors were just discovered above. Only for baseline
        # runs, same as identity/competitor discovery; a monitoring run
        # doesn't need a fresh question set every week, just fresh answers
        # to the ones that already exist (Phase 11).
        if run.run_type == ResearchRunType.baseline and identity is not None:
            question_agent_run = _start_agent_run(session, run.id, "visibility_question_generation_agent_run")
            try:
                generated_questions, question_evidence_ids = await generate_visibility_questions(
                    session=session,
                    router=self._router,
                    store_id=store.id,
                    research_run_id=run.id,
                    agent_run_id=question_agent_run.id,
                    identity=identity,
                    competitor_names=[c.name for c in discovered_competitors],
                )
            except Exception as exc:  # noqa: BLE001 — question generation failing must never block the run
                session.rollback()
                _fail_agent_run(session, question_agent_run, str(exc))
            else:
                _complete_agent_run(
                    session,
                    question_agent_run,
                    findings={"questions_generated": len(generated_questions)},
                    evidence_ids=[str(e) for e in question_evidence_ids],
                )

        classification_agent_run = _start_agent_run(session, run.id, "ai_classification_agent_run")
        if not has_sufficient_observations_for_classification(observations):
            # business_type is a required field on StoreClassification, so
            # calling the model from a near-empty crawl would still produce
            # *some* answer — a plausible-looking but essentially fabricated
            # classification, not an honest "not enough data." Skip the call
            # entirely and record why, the same "found nothing is still a
            # normal completion" pattern used elsewhere (e.g. empty intents).
            _complete_agent_run(
                session,
                classification_agent_run,
                findings={
                    "skipped": True,
                    "reason": "insufficient_observations",
                    "observations_count": len(observations),
                    "min_required": MIN_OBSERVATIONS_FOR_CLASSIFICATION,
                },
                evidence_ids=[],
            )
        else:
            try:
                classification, evidence_id = await run_store_classification_agent(
                    session=session,
                    router=self._router,
                    store_id=store.id,
                    research_run_id=run.id,
                    agent_run_id=classification_agent_run.id,
                    observations=observations,
                )
                _complete_agent_run(
                    session,
                    classification_agent_run,
                    findings=classification.model_dump() if classification else None,
                    evidence_ids=[str(evidence_id)] if evidence_id else [],
                )
            except Exception as exc:  # noqa: BLE001 — classification is enrichment; a failure here doesn't invalidate the crawl
                session.rollback()  # a failed flush leaves the session unusable until rolled back
                _fail_agent_run(session, classification_agent_run, str(exc))

        update_component_snapshot(
            session, store_id=store.id, research_run_id=run.id,
            component="basic", status="completed",
            progress_completed=len(observations), progress_total=len(observations),
            payload={"pages_crawled": len(observations)},
        )

        # A background expansion enriches crawl/catalog facts only. Search,
        # scoring, and recommendations from the baseline are not repeated.
        if run.run_type == ResearchRunType.verification:
            run.status = RunStatus.completed
            run.completed_at = utcnow()
            store.status = StoreStatus.active
            session.add(run)
            session.add(store)
            session.commit()
            session.refresh(run)
            return run

        # Part R2-F1 — never silently invent a market. Locale resolution
        # (deterministic signals, plus an AI last resort) already ran
        # inside run_crawl_agent; if it's still unresolved here, the
        # configured default is used but the fact that a fallback fired
        # is now always recorded (see findings below), never silent —
        # this is exactly the bug Round 2 confirmed on glossier.com/
        # chewy.com (measured as Saudi/Arabic with no trace of why).
        locale_fallback_used = store.locale_status != "resolved"
        country = store.country or self._settings.serp_default_country
        language = store.language or self._settings.serp_default_language

        categories = session.exec(select(Category).where(Category.store_id == store.id)).all()
        products = session.exec(select(Product).where(Product.store_id == store.id)).all()

        fallback_page_titles: list[str] | None = None
        if not categories and not products:
            # URL-pattern page classification found no product/category
            # pages (common on Salla/Zid-style stores) — fall back to raw
            # crawled page titles/H1s so AI expansion has *something* real
            # to work from instead of an empty catalog.
            page_observations = session.exec(
                select(PageObservation).where(PageObservation.research_run_id == run.id)
            ).all()
            fallback_page_titles = [
                (obs.normalized_extraction or {}).get("title") or (obs.normalized_extraction or {}).get("h1")
                for obs in page_observations
            ]
            fallback_page_titles = [title for title in fallback_page_titles if title]

        identity_context: str | None = None
        if not categories and not products and not fallback_page_titles and identity is not None:
            # The true fully-empty-crawl case — nothing at all was crawled,
            # but identity resolution (above) still found something real
            # via web search. Give intent expansion a non-fabricated basis
            # to work from instead of "(لا توجد بيانات كتالوج)".
            identity_lines = []
            if identity.business_type:
                identity_lines.append(f"نوع النشاط: {identity.business_type}")
            if identity.categories:
                identity_lines.append(f"التصنيفات: {', '.join(identity.categories)}")
            if identity.target_audiences:
                identity_lines.append(f"الجمهور المستهدف: {', '.join(identity.target_audiences)}")
            if identity.market_signals:
                identity_lines.append(f"مؤشرات السوق: {', '.join(identity.market_signals)}")
            identity_context = "\n".join(identity_lines) or None

        intent_agent_run = _start_agent_run(session, run.id, "intent_agent_run")
        intents = []
        try:
            intents = generate_deterministic_seed_intents(
                session,
                store_id=store.id,
                research_run_id=run.id,
                categories=categories,
                country=country,
                language=language,
                max_intents=self._settings.intent_max_per_run,
            )
        except Exception as exc:  # noqa: BLE001 — no catalog data to seed from means this step genuinely failed
            session.rollback()
            _fail_agent_run(session, intent_agent_run, str(exc))
        else:
            # AI expansion is enrichment on top of the deterministic seeds
            # (same relationship as classification is to the crawl) — its
            # failure must not erase the seeds already generated above.
            try:
                intents += await run_intent_expansion_agent(
                    session=session,
                    router=self._router,
                    store_id=store.id,
                    research_run_id=run.id,
                    agent_run_id=intent_agent_run.id,
                    categories=categories,
                    products=products,
                    fallback_page_titles=fallback_page_titles,
                    identity_context=identity_context,
                    country=country,
                    language=language,
                    max_intents=self._settings.intent_max_per_run,
                    already_generated=len(intents),
                )
            except Exception:  # noqa: BLE001
                session.rollback()

            # Part G-B1 — deterministic quality gate. Every generated Intent
            # is scored and persisted either way; only the accepted subset
            # proceeds to SERP/AI-visibility measurement and downstream
            # opportunity detection.
            intents_before_gate = len(intents)
            intents = apply_quality_gate(session, intents, store.id)
            # Part Q1 — groups the accepted intents into topics beyond
            # G-B1's near-duplicate rejection (which only drops
            # near-identical phrasings of the same question). Deterministic,
            # no AI call, so it never blocks the run even if it finds
            # nothing worth grouping (e.g. a single accepted intent).
            clusters = cluster_intents(session, store.id, run.id, intents)
            _complete_agent_run(
                session,
                intent_agent_run,
                findings={
                    "intents_generated": intents_before_gate,
                    "intents_accepted": len(intents),
                    "intent_clusters": len(clusters),
                    "locale_fallback_used": locale_fallback_used,
                    "measured_country": country,
                    "measured_language": language,
                },
            )

        update_component_snapshot(
            session, store_id=store.id, research_run_id=run.id,
            component="google", status="running", progress_total=len(intents),
        )
        serp_agent_run = _start_agent_run(session, run.id, "serp_agent_run")
        try:
            serp_observations = await run_serp_agent(
                session=session,
                search_provider=self._search_provider,
                store_id=store.id,
                store_url=store.url,
                research_run_id=run.id,
                agent_run_id=serp_agent_run.id,
                intents=intents,
                country=country,
                language=language,
                num_results=self._settings.serp_num_results,
                max_queries=self._settings.serp_max_queries_per_run,
                storage=self._storage,
                max_concurrency=self._settings.serp_max_concurrency,
            )
            # Part G-B5: SERP-sourced competitors are seeded here, right
            # after SERP measurement and *before* ai_visibility_batch runs
            # — deliberately not deferred to the iterative loop's seed task
            # (as it used to be). detect_competitors_mentioned
            # (app.ai_visibility.visibility_engine) can only match a
            # competitor's domain in the AI's response text if that
            # Competitor row already exists; on a store's first-ever run it
            # never did, silently starving detect_ai_citation_gap_
            # opportunities of its only realistic evidence source (AI
            # rarely returns raw citation URLs with no search grounding
            # enabled — Part C #4). mine_ai_visibility_competitors (the
            # other half) still runs later, once, as the loop's seed task.
            mine_serp_competitors(session, store.id, store.url, run.id)
            _complete_agent_run(session, serp_agent_run, findings={"queries_measured": len(serp_observations)})
            update_component_snapshot(
                session, store_id=store.id, research_run_id=run.id,
                component="google", status="completed",
                progress_completed=len(serp_observations), progress_total=len(intents),
                payload={"queries_measured": len(serp_observations)},
            )
        except Exception as exc:  # noqa: BLE001 — SERP failing doesn't invalidate everything measured so far
            session.rollback()
            _fail_agent_run(session, serp_agent_run, str(exc))
            update_component_snapshot(
                session, store_id=store.id, research_run_id=run.id,
                component="google", status="failed", error=str(exc),
            )

        prompt_family_agent_run = _start_agent_run(session, run.id, "prompt_family_agent_run")
        prompt_variants = []
        try:
            top_intents = select_top_intents(session, run.id, max_intents=self._settings.ai_visibility_max_intents_per_run)
            prompt_variants = await run_prompt_family_agent(
                session=session,
                router=self._router,
                research_run_id=run.id,
                agent_run_id=prompt_family_agent_run.id,
                intents=top_intents,
                max_prompts_per_intent=self._settings.ai_visibility_prompt_variants_per_intent,
            )
            _complete_agent_run(
                session, prompt_family_agent_run, findings={"prompt_variants_generated": len(prompt_variants)}
            )
        except Exception as exc:  # noqa: BLE001 — no prompts to test means the next step just does nothing, not a hard failure
            session.rollback()
            _fail_agent_run(session, prompt_family_agent_run, str(exc))

        update_component_snapshot(
            session, store_id=store.id, research_run_id=run.id,
            component="ai", status="running", progress_total=len(prompt_variants),
        )
        ai_visibility_agent_run = _start_agent_run(session, run.id, "ai_visibility_agent_run")
        try:
            surfaces = resolve_configured_engines(self._router)
            ai_visibility_observations = await run_ai_visibility_agent(
                session=session,
                router=self._router,
                store_id=store.id,
                store_url=store.url,
                research_run_id=run.id,
                agent_run_id=ai_visibility_agent_run.id,
                prompt_variants=prompt_variants,
                surfaces=surfaces,
                country=country,
                language=language,
                repetitions=self._settings.ai_visibility_repetitions,
                storage=self._storage,
                evaluation_mode=self._settings.evaluation_mode,
                max_concurrency=self._settings.ai_max_concurrency,
            )
            _complete_agent_run(
                session, ai_visibility_agent_run, findings={"observations_recorded": len(ai_visibility_observations)}
            )
            update_component_snapshot(
                session, store_id=store.id, research_run_id=run.id,
                component="ai", status="completed",
                progress_completed=len(ai_visibility_observations), progress_total=len(prompt_variants),
                payload={"observations_recorded": len(ai_visibility_observations)},
            )
        except Exception as exc:  # noqa: BLE001 — AI visibility failing doesn't invalidate everything measured so far
            session.rollback()
            _fail_agent_run(session, ai_visibility_agent_run, str(exc))
            update_component_snapshot(
                session, store_id=store.id, research_run_id=run.id,
                component="ai", status="failed", error=str(exc),
            )

        # Group D2: competitor_discovery_agent_run + page_intelligence_agent_run
        # (fixed, one-shot steps) are superseded by one iterative research
        # loop — discovery becomes the loop's seed task, and page
        # intelligence becomes Planner-proposed competitor_deep_dive/
        # page_compare follow-ups sized to what was actually found, not a
        # fixed batch every time.
        update_component_snapshot(
            session, store_id=store.id, research_run_id=run.id,
            component="competitors", status="running",
        )
        iterative_research_agent_run = _start_agent_run(session, run.id, "iterative_research_agent_run")
        # Part H8 — set when the loop stops specifically because
        # cancellation was requested, so the final run.status below reads
        # RunStatus.cancelled instead of RunStatus.completed; every step
        # after this one still runs against whatever research did complete,
        # same as any other early stop reason.
        was_cancelled = False
        try:
            metrics = await run_iterative_research_loop(
                session=session,
                router=self._router,
                storage=self._storage,
                search_provider=self._search_provider,
                settings=self._settings,
                store=store,
                run=run,
                agent_run_id=iterative_research_agent_run.id,
            )
            was_cancelled = metrics.stop_reason == CANCELLATION_STOP_REASON
            _complete_agent_run(session, iterative_research_agent_run, findings=dataclasses.asdict(metrics))
            update_component_snapshot(
                session, store_id=store.id, research_run_id=run.id,
                component="competitors", status="completed", payload=dataclasses.asdict(metrics),
            )
        except Exception as exc:  # noqa: BLE001 — research loop failing doesn't invalidate everything measured by the fixed phases above
            session.rollback()
            _fail_agent_run(session, iterative_research_agent_run, str(exc))
            update_component_snapshot(
                session, store_id=store.id, research_run_id=run.id,
                component="competitors", status="failed", error=str(exc),
            )

        # Group E: turns everything gathered above into a small number of
        # evidence-backed opportunities and recommendations — the layer the
        # customer actually sees ("what should I do now?"), not raw research.
        update_component_snapshot(
            session, store_id=store.id, research_run_id=run.id,
            component="opportunities", status="running",
        )
        opportunity_recommendation_agent_run = _start_agent_run(session, run.id, "opportunity_recommendation_agent_run")
        try:
            opportunities = run_opportunity_discovery_agent(session, store.id, run.id)
            backfill_task_opportunity_impact(session, run.id, opportunities)
            recommendations = run_recommendation_engine(
                session,
                store.id,
                run.id,
                opportunities,
                max_recommendations=self._settings.recommendation_max_per_run,
            )

            # Part Q3 — quality-gate the primary queue (same freshness-
            # gated "top N by priority, reconfirmed by this run" selection
            # the API/harness use for is_primary — Part R2), not everything
            # ever generated for this store. `run` isn't marked completed
            # until after execute_run() returns, so as_of_run_id is passed
            # explicitly rather than relying on run.status in the DB.
            # Report-only: a failing check never blocks the run, it just
            # surfaces in findings/EvaluationSummary for the benchmark/
            # replay review the directive asks for before any live round.
            primary_queue = select_primary_recommendations(
                session, store.id, self._settings.recommendation_primary_queue_size, as_of_run_id=run.id
            )
            quality_issues = check_recommendation_batch_quality(primary_queue)

            _complete_agent_run(
                session,
                opportunity_recommendation_agent_run,
                findings={
                    "opportunities_found": len(opportunities),
                    "recommendations_generated": len(recommendations),
                    "primary_queue_size": len(primary_queue),
                    "quality_issues_found": len(quality_issues),
                    "quality_issue_checks": sorted({i.check for i in quality_issues}),
                },
            )
            update_component_snapshot(
                session, store_id=store.id, research_run_id=run.id,
                component="opportunities", status="completed",
                progress_completed=len(recommendations), progress_total=len(recommendations),
                payload={"opportunities_found": len(opportunities), "recommendations_generated": len(recommendations)},
            )
        except Exception as exc:  # noqa: BLE001 — opportunity/recommendation generation failing doesn't invalidate the research already completed
            session.rollback()
            _fail_agent_run(session, opportunity_recommendation_agent_run, str(exc))

        if opportunity_recommendation_agent_run.status == RunStatus.failed:
            update_component_snapshot(
                session, store_id=store.id, research_run_id=run.id,
                component="opportunities", status="failed",
                error=opportunity_recommendation_agent_run.error,
            )

        # Group F1-F5 + F8 combined: both look at "what changed since the
        # last run?" (implementation detection/outcome reclassification vs.
        # competitor/visibility deltas + alerts), so they share one step
        # rather than adding two more agent_runs.
        monitoring_and_alerts_agent_run = _start_agent_run(session, run.id, "monitoring_and_alerts_agent_run")
        try:
            monitoring_summary = await run_monitoring_pass(
                session, store, run.id,
                search_provider=self._search_provider, router=self._router,
                ai_surfaces=resolve_configured_engines(self._router), agent_run_id=monitoring_and_alerts_agent_run.id,
                evaluation_mode=self._settings.evaluation_mode,
            )
            alerts = generate_alerts(session, store, run)
            _complete_agent_run(
                session,
                monitoring_and_alerts_agent_run,
                findings={**monitoring_summary, "alerts_generated": len(alerts)},
            )
        except Exception as exc:  # noqa: BLE001 — monitoring/alerts failing doesn't invalidate the research already completed
            session.rollback()
            _fail_agent_run(session, monitoring_and_alerts_agent_run, str(exc))

        run.status = RunStatus.cancelled if was_cancelled else RunStatus.completed
        run.completed_at = utcnow()
        session.add(run)

        store.status = StoreStatus.active
        # Group F7: (re)schedule the next monitoring run every time any run
        # completes — this both starts the schedule after the first
        # baseline and re-arms it after each subsequent monitoring run.
        # "manual" cadence (or any unrecognized value) yields None, i.e.
        # never auto-scheduled.
        store.next_scheduled_run_at = compute_next_scheduled_run_at(store.monitoring_cadence, utcnow())
        session.add(store)

        session.commit()
        session.refresh(run)
        return run
