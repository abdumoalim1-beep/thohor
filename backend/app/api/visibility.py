import uuid
from collections import Counter, defaultdict
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from app.ai_visibility.multi_engine_runner import create_pending_visibility_run
from app.ai_visibility.visibility_metrics_v2 import (
    compute_client_rank_among_competitors,
    compute_top_citations,
    compute_top_competitors,
    compute_visibility_metrics,
    compute_week_over_week_delta,
)
from app.ai_visibility.visibility_opportunities import derive_top_opportunities
from app.api.schemas import (
    TriggerVisibilityRunResponse,
    VisibilityAnswerItem,
    VisibilityCitationItem,
    VisibilityCompetitorMentionItem,
    VisibilityCompetitorSummaryItem,
    VisibilityMetricsSummary,
    VisibilityOpportunityItem,
    VisibilityQuestionItem,
    VisibilityRunDetailResponse,
    VisibilitySignupReport,
    VisibilitySourceItem,
    VisibilitySourceSummaryItem,
    VisibilityTopCompetitorItem,
)
from app.competitors.citation_classification import classify_citation_source_type
from app.core.db import get_session
from app.core.urls import normalize_hostname
from app.models.competitor import Competitor
from app.models.store import Store
from app.models.visibility_run import EngineAnswer, EngineAnswerAnalysis, VisibilityQuestion, VisibilityRun
from app.workers.tasks import execute_visibility_run_task

router = APIRouter(prefix="/stores", tags=["visibility"])


@router.post("/{store_id}/visibility-runs", response_model=TriggerVisibilityRunResponse)
def trigger_visibility_run(store_id: uuid.UUID, session: Session = Depends(get_session)) -> TriggerVisibilityRunResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    latest = session.exec(
        select(VisibilityRun).where(VisibilityRun.store_id == store_id).order_by(VisibilityRun.started_at.desc())  # type: ignore[union-attr]
    ).first()
    if latest is not None and latest.status == "running":
        raise HTTPException(status_code=409, detail="a visibility run is already in progress for this store")

    # Real bug caught live: understanding_stage (and therefore /signup's
    # "identity ready, start analyzing" auto-trigger) can go "ready" right
    # after identity resolves — a full step *before* question generation
    # (a later, separate step in the same baseline research run) has
    # actually produced any VisibilityQuestion rows. Triggering anyway used
    # to silently create a run that completed instantly with 0 questions
    # measured — no error, indistinguishable from "finished analyzing" with
    # nothing to show. Refuse instead, so the caller retries once questions
    # actually exist.
    has_questions = session.exec(
        select(VisibilityQuestion.id).where(VisibilityQuestion.store_id == store_id, VisibilityQuestion.is_active == True)  # noqa: E712
    ).first()
    if has_questions is None:
        return TriggerVisibilityRunResponse(visibility_run_id=None, status="not_ready")

    run = create_pending_visibility_run(session, store_id)
    execute_visibility_run_task.delay(str(store_id), str(run.id))
    return TriggerVisibilityRunResponse(visibility_run_id=run.id, status=run.status)


@router.get("/{store_id}/visibility-runs/latest", response_model=VisibilityRunDetailResponse)
def get_latest_visibility_run(store_id: uuid.UUID, session: Session = Depends(get_session)) -> VisibilityRunDetailResponse:
    store = session.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="store not found")

    run = session.exec(
        select(VisibilityRun)
        .where(VisibilityRun.store_id == store_id, VisibilityRun.status != "running")
        .order_by(VisibilityRun.completed_at.desc())  # type: ignore[union-attr]
    ).first()
    if run is None:
        # A run may still be in flight (triggered but not completed) — say so
        # honestly rather than silently reporting "no run yet" either way.
        # The unified "تحليل ظهور علامتك" progress screen needs a live
        # completed/total count, not the full report (not meaningful yet
        # mid-run) — cheap enough to compute on every poll (a single
        # COUNT(*) against the run's own EngineAnswer rows).
        in_flight = session.exec(
            select(VisibilityRun)
            .where(VisibilityRun.store_id == store_id, VisibilityRun.status == "running")
            # Normally at most one running row exists (the 409 duplicate
            # guard prevents a second). A worker crash/restart mid-task can
            # still leave an older stuck row behind an unrelated newer one
            # (observed live) — always poll the most recently started one.
            .order_by(VisibilityRun.started_at.desc())  # type: ignore[union-attr]
        ).first()
        if in_flight is None:
            return VisibilityRunDetailResponse(status="no_run_yet")
        completed_count = session.exec(
            select(func.count()).select_from(EngineAnswer).where(EngineAnswer.visibility_run_id == in_flight.id)
        ).one()
        return VisibilityRunDetailResponse(
            status="running", run_id=in_flight.id,
            completed_count=completed_count, total_planned=in_flight.total_operations_planned,
        )

    answers = session.exec(select(EngineAnswer).where(EngineAnswer.visibility_run_id == run.id)).all()
    answer_ids = [a.id for a in answers]
    analyses = session.exec(
        select(EngineAnswerAnalysis).where(EngineAnswerAnalysis.engine_answer_id.in_(answer_ids))  # type: ignore[attr-defined]
    ).all() if answer_ids else []
    analyses_by_answer = {a.engine_answer_id: a for a in analyses}

    client_hostname = normalize_hostname(urlparse(store.url).hostname or "")
    all_competitors = session.exec(select(Competitor).where(Competitor.store_id == store_id)).all()
    competitor_domains = {c.domain for c in all_competitors}
    competitor_name_to_domain = {c.name: c.domain for c in all_competitors}

    metrics = compute_visibility_metrics(session, run.id, client_hostname)
    week_over_week = compute_week_over_week_delta(session, store_id, run.id, metrics, client_hostname)
    summary = VisibilityMetricsSummary(
        successful_answers=metrics.successful_answers, mention_rate=metrics.mention_rate,
        recommendation_rate=metrics.recommendation_rate, avg_recommendation_rank=metrics.avg_recommendation_rank,
        top_3_rate=metrics.top_3_rate, share_of_voice=metrics.share_of_voice, citation_rate=metrics.citation_rate,
        top_competitor=metrics.top_competitor, top_competitor_mentions=metrics.top_competitor_mentions,
        week_over_week=week_over_week,
    )

    questions = session.exec(select(VisibilityQuestion).where(VisibilityQuestion.store_id == store_id)).all()
    questions_by_id = {q.id: q for q in questions}
    answers_by_question: dict[uuid.UUID, list[EngineAnswer]] = defaultdict(list)
    for answer in answers:
        answers_by_question[answer.question_id].append(answer)

    competitor_counter: Counter[str] = Counter()
    source_counter: dict[str, dict] = {}

    question_items: list[VisibilityQuestionItem] = []
    for question_id, question_answers in answers_by_question.items():
        question = questions_by_id.get(question_id)
        if question is None:
            continue
        answer_items: list[VisibilityAnswerItem] = []
        for answer in question_answers:
            analysis = analyses_by_answer.get(answer.id)
            source_items: list[VisibilitySourceItem] = []
            for source in answer.sources:
                url = source.get("url", "")
                title = source.get("title", "")
                source_type = classify_citation_source_type(
                    url, client_hostname=client_hostname, competitor_domains=competitor_domains
                )
                source_items.append(VisibilitySourceItem(url=url, title=title, source_type=source_type))
                key = url
                if key not in source_counter:
                    source_counter[key] = {"url": url, "title": title, "source_type": source_type, "count": 0}
                source_counter[key]["count"] += 1

            competitors_mentioned: list[VisibilityCompetitorMentionItem] = []
            if analysis is not None:
                for competitor in analysis.competitors_mentioned:
                    name = competitor.get("name") if isinstance(competitor, dict) else None
                    if not name:
                        continue
                    competitor_counter[name] += 1
                    competitors_mentioned.append(
                        VisibilityCompetitorMentionItem(name=name, rank=competitor.get("rank"))
                    )

            answer_items.append(VisibilityAnswerItem(
                engine=answer.engine, status=answer.status, raw_answer=answer.raw_answer,
                brand_mentioned=analysis.brand_mentioned if analysis else None,
                mention_type=analysis.mention_type if analysis else None,
                mention_rank=analysis.mention_rank if analysis else None,
                recommendation_rank=analysis.recommendation_rank if analysis else None,
                evidence_quote=analysis.evidence_quote if analysis else None,
                competitors_mentioned=competitors_mentioned, sources=source_items,
            ))

        question_items.append(VisibilityQuestionItem(
            question_id=question.id, text=question.text, category=question.category, answers=answer_items,
        ))

    competitors_summary = [
        VisibilityCompetitorSummaryItem(name=name, mentions=count)
        for name, count in competitor_counter.most_common(20)
    ]
    sources_summary = [
        VisibilitySourceSummaryItem(**s) for s in sorted(source_counter.values(), key=lambda s: -s["count"])[:30]
    ]

    # SIGNUP re-scope — one merged, engine-agnostic report block. Reuses
    # the exact same metrics/competitor-discovery/answer-analysis data
    # already computed above; no separate calculation path.
    all_competitors_ranked = compute_top_competitors(
        session, run.id, client_avg_mention_rank=metrics.avg_mention_rank,
        competitor_name_to_domain=competitor_name_to_domain, limit=None,
    )
    top_competitors = all_competitors_ranked[:5]
    client_rank, competitors_considered_count = compute_client_rank_among_competitors(
        metrics.mentioned_count, [c.appearances for c in all_competitors_ranked]
    )
    citations = compute_top_citations(
        session, run.id, client_hostname=client_hostname, competitor_domain_names=competitor_name_to_domain,
    )
    opportunities = derive_top_opportunities(metrics, top_competitors)
    report = VisibilitySignupReport(
        total_searches=metrics.total_searches, mentioned_count=metrics.mentioned_count,
        appearance_rate=metrics.mention_rate, avg_rank=metrics.avg_mention_rank, top3_count=metrics.top3_count,
        competitors_ahead_count=sum(1 for c in top_competitors if c.ahead_of_client),
        client_rank=client_rank, competitors_considered_count=competitors_considered_count,
        top_competitors=[
            VisibilityTopCompetitorItem(
                name=c.name, domain=c.domain, appearances=c.appearances, appearance_rate=c.appearance_rate,
                avg_rank=c.avg_rank, ahead_of_client=c.ahead_of_client,
            )
            for c in top_competitors
        ],
        citations=[
            VisibilityCitationItem(domain=c.domain, citation_count=c.citation_count, supports=c.supports)
            for c in citations
        ],
        opportunities=[
            VisibilityOpportunityItem(title=o.title, reason=o.reason, evidence=o.evidence, actions=o.actions)
            for o in opportunities
        ],
    )

    return VisibilityRunDetailResponse(
        run_id=run.id, status=run.status,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        engines_attempted=run.engines_attempted, summary=summary, questions=question_items,
        competitors=competitors_summary, sources=sources_summary, report=report,
    )
