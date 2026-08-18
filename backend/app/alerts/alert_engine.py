import uuid

from sqlmodel import Session, select

from app.ai_visibility.metrics import compute_ai_visibility_metrics
from app.core.urls import normalize_hostname
from app.models.alert import Alert
from app.models.competitor import Competitor
from app.models.measurement import MeasurementSnapshot
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
from app.models.stable_intent import StableIntent
from app.models.store import Store

AI_VISIBILITY_DROP_THRESHOLD = 0.15
HIGH_PRIORITY_OPPORTUNITY_THRESHOLD = 75.0


def _find_previous_completed_run(session: Session, store_id: uuid.UUID, current_run_id: uuid.UUID) -> ResearchRun | None:
    from app.models.research import RunStatus

    return session.exec(
        select(ResearchRun)
        .where(ResearchRun.store_id == store_id)
        .where(ResearchRun.id != current_run_id)
        .where(ResearchRun.status == RunStatus.completed)
        .order_by(ResearchRun.created_at.desc())  # type: ignore[arg-type]
    ).first()


def _detect_competitor_overtook(session: Session, store: Store, run: ResearchRun, previous_run_id: uuid.UUID) -> list[Alert]:
    """Keyed by stable_intent_id (Part F.5-0), not the run-scoped intent_id
    — SerpObservation.intent_id never matches across two different
    research_runs (each run creates brand-new Intent rows), which silently
    zeroed this alert out before stable identity existed."""
    current_by_intent = {
        o.stable_intent_id: o
        for o in session.exec(select(SerpObservation).where(SerpObservation.research_run_id == run.id)).all()
        if o.stable_intent_id is not None
    }
    previous_by_intent = {
        o.stable_intent_id: o
        for o in session.exec(select(SerpObservation).where(SerpObservation.research_run_id == previous_run_id)).all()
        if o.stable_intent_id is not None
    }

    alerts: list[Alert] = []
    for stable_intent_id, current in current_by_intent.items():
        previous = previous_by_intent.get(stable_intent_id)
        if previous is None or previous.client_rank is None:
            continue
        got_worse = current.client_rank is None or current.client_rank > previous.client_rank
        if not got_worse or not current.results:
            continue

        top_result = current.results[0]
        stable_intent = session.get(StableIntent, stable_intent_id)
        alerts.append(
            Alert(
                store_id=store.id,
                research_run_id=run.id,
                alert_type="competitor_overtook",
                severity="warning",
                title="منافس تجاوزك في نتائج البحث",
                message=(
                    f"تراجع ترتيبك لنية '{stable_intent.canonical_topic if stable_intent else stable_intent_id}' "
                    f"من {previous.client_rank} إلى {current.client_rank or 'خارج النتائج'}، "
                    f"بينما {top_result.get('domain', 'منافس')} يتصدر الآن."
                ),
            )
        )
    return alerts


def _detect_ai_visibility_dropped(session: Session, store: Store, run: ResearchRun, previous_run_id: uuid.UUID) -> list[Alert]:
    current_metrics = compute_ai_visibility_metrics(session, run.id)
    previous_metrics = compute_ai_visibility_metrics(session, previous_run_id)
    if previous_metrics.total_observations == 0 or current_metrics.total_observations == 0:
        return []

    drop = previous_metrics.mention_rate - current_metrics.mention_rate
    if drop < AI_VISIBILITY_DROP_THRESHOLD:
        return []

    return [
        Alert(
            store_id=store.id,
            research_run_id=run.id,
            alert_type="ai_visibility_dropped",
            severity="warning",
            title="انخفض ظهور متجرك في محركات AI",
            message=f"انخفضت نسبة الذكر من {previous_metrics.mention_rate:.0%} إلى {current_metrics.mention_rate:.0%}.",
        )
    ]


def _detect_new_competitors(session: Session, store: Store, run: ResearchRun) -> list[Alert]:
    new_competitors = session.exec(
        select(Competitor).where(Competitor.store_id == store.id).where(Competitor.first_seen_research_run_id == run.id)
    ).all()

    return [
        Alert(
            store_id=store.id,
            research_run_id=run.id,
            alert_type="new_competitor",
            severity="info",
            title="اكتشفنا منافسًا جديدًا",
            message=f"{normalize_hostname(c.domain)} ظهر كمنافس جديد لأول مرة هذا التشغيل.",
            related_competitor_id=c.id,
        )
        for c in new_competitors
    ]


def _detect_recommendations_showing_results(session: Session, store: Store, run: ResearchRun) -> list[Alert]:
    snapshots_this_run = session.exec(
        select(MeasurementSnapshot).where(MeasurementSnapshot.research_run_id == run.id)
    ).all()

    alerts: list[Alert] = []
    for snapshot in snapshots_this_run:
        recommendation = session.get(Recommendation, snapshot.recommendation_id)
        if recommendation is None or recommendation.status != RecommendationStatus.successful:
            continue
        alerts.append(
            Alert(
                store_id=store.id,
                research_run_id=run.id,
                alert_type="recommendation_showing_results",
                severity="success",
                title="التوصية التي نفذتها بدأت تظهر نتائج",
                message=f"لوحظ تحسّن ملموس بعد تنفيذ توصية '{recommendation.title}'.",
                related_recommendation_id=recommendation.id,
            )
        )
    return alerts


def _detect_new_high_priority_opportunities(session: Session, store: Store, run: ResearchRun) -> list[Alert]:
    from app.models.opportunity import Opportunity

    new_opportunities = session.exec(
        select(Opportunity)
        .where(Opportunity.store_id == store.id)
        .where(Opportunity.research_run_id == run.id)
        .where(Opportunity.priority_score >= HIGH_PRIORITY_OPPORTUNITY_THRESHOLD)
    ).all()
    # "New" = first ever seen this run, not just touched/updated this run.
    genuinely_new = [o for o in new_opportunities if run.started_at is None or o.created_at >= run.started_at]

    return [
        Alert(
            store_id=store.id,
            research_run_id=run.id,
            alert_type="new_high_priority_opportunity",
            severity="info",
            title="ظهرت فرصة جديدة ذات أولوية عالية",
            message=f"'{o.title}' — أولوية {o.priority_score:.0f}/100.",
        )
        for o in genuinely_new
    ]


def generate_alerts(session: Session, store: Store, run: ResearchRun) -> list[Alert]:
    """Five deterministic rules (Group F8 — 'page regression' deferred as a
    documented V1 cut, it needs deeper diffing than a single hash
    comparison gives). Every rule compares this run against the most
    recent *completed* prior run for the same store — the very first
    baseline naturally produces zero alerts here since there's nothing to
    compare against yet."""
    previous_run = _find_previous_completed_run(session, store.id, run.id)

    alerts: list[Alert] = []
    if previous_run is not None:
        alerts.extend(_detect_competitor_overtook(session, store, run, previous_run.id))
        alerts.extend(_detect_ai_visibility_dropped(session, store, run, previous_run.id))
        alerts.extend(_detect_new_competitors(session, store, run))

    alerts.extend(_detect_recommendations_showing_results(session, store, run))
    alerts.extend(_detect_new_high_priority_opportunities(session, store, run))

    for alert in alerts:
        session.add(alert)
    session.commit()
    for alert in alerts:
        session.refresh(alert)

    return alerts
