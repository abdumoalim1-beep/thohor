"""SIGNUP re-scope — exactly 2 recommendations, both derived directly from
this scan's own computed metrics/competitors, never a generic unsupported
suggestion. Deliberately not the existing Opportunity/Recommendation engine
(app.opportunities.*) — that system detects catalog/SEO gaps from crawled
pages; this reads the visibility-scan numbers that already exist by the
time this runs, no new AI call, no new detection framework. Each candidate
only exists if its evidence condition is actually true; fewer than 2 real
findings means fewer than 2 recommendations shown, never padded."""

from dataclasses import dataclass

from app.ai_visibility.visibility_metrics_v2 import CompetitorVisibilitySummary, VisibilityMetricsV2

MIN_SAMPLE_FOR_CONFIDENT_FINDING = 10


@dataclass
class VisibilityOpportunity:
    title: str
    reason: str
    evidence: str
    actions: list[str]
    priority: float  # impact * confidence, used only to rank candidates


def _very_low_overall_visibility(metrics: VisibilityMetricsV2) -> VisibilityOpportunity | None:
    if metrics.successful_answers < MIN_SAMPLE_FOR_CONFIDENT_FINDING or metrics.mention_rate is None:
        return None
    if metrics.mention_rate >= 0.15:
        return None
    impact = 1.0 - metrics.mention_rate
    confidence = min(1.0, metrics.successful_answers / 50)
    return VisibilityOpportunity(
        title="علامتك تكاد تكون غائبة عندما يبحث عملاؤك",
        reason="أغلب عمليات البحث التي تعكس نية شراء حقيقية لم تُظهر متجرك إطلاقًا.",
        evidence=f"ظهرت علامتك في {metrics.mentioned_count} فقط من أصل {metrics.successful_answers} عملية بحث تم تحليلها.",
        actions=[
            "أضف محتوى واضحًا يصف منتجاتك وفئاتك بلغة طبيعية يفهمها الذكاء الاصطناعي، لا فقط كلمات SEO.",
            "تأكد أن صفحات منتجاتك تحتوي أسماء وأوصافًا حقيقية وواضحة، لا صورًا فقط.",
        ],
        priority=impact * confidence,
    )


def _citation_gap(metrics: VisibilityMetricsV2) -> VisibilityOpportunity | None:
    if metrics.citation_rate is None or metrics.successful_answers < MIN_SAMPLE_FOR_CONFIDENT_FINDING:
        return None
    if metrics.citation_rate >= 0.3:
        return None
    impact = 1.0 - metrics.citation_rate
    confidence = 0.7
    return VisibilityOpportunity(
        title="مصادر الإجابات نادرًا ما تشير إلى موقعك مباشرة",
        reason="الإجابات التي استندت إلى مصادر خارجية اعتمدت غالبًا على مواقع أخرى بدل موقعك.",
        evidence=f"نسبة الإجابات التي أشارت مصادرها إلى موقعك: {round(metrics.citation_rate * 100)}% فقط.",
        actions=[
            "أضف صفحة \"عن المتجر\" ومعلومات تواصل وموقع واضحة يسهل على محركات البحث والذكاء الاصطناعي فهمها والاستشهاد بها.",
        ],
        priority=impact * confidence,
    )


def _competitor_ahead_gap(metrics: VisibilityMetricsV2, top_competitors: list[CompetitorVisibilitySummary]) -> VisibilityOpportunity | None:
    if not top_competitors or metrics.successful_answers < MIN_SAMPLE_FOR_CONFIDENT_FINDING:
        return None
    leader = top_competitors[0]
    if not leader.ahead_of_client or leader.appearances <= metrics.mentioned_count:
        return None
    gap = leader.appearances - metrics.mentioned_count
    impact = min(1.0, gap / max(metrics.successful_answers, 1))
    confidence = 0.8
    client_rank_text = f"{metrics.avg_mention_rank:.1f}" if metrics.avg_mention_rank is not None else "غير معروف"
    leader_rank_text = f"{leader.avg_rank:.1f}" if leader.avg_rank is not None else "غير معروف"
    return VisibilityOpportunity(
        title=f"منافس واحد يظهر قبلك في أغلب عمليات البحث",
        reason=f"{leader.name} يظهر بشكل أكثر ثباتًا وبترتيب أفضل من متجرك في نفس عمليات البحث.",
        evidence=(
            f"ظهر {leader.name} في {leader.appearances} عملية بحث بمتوسط ترتيب {leader_rank_text}، "
            f"مقابل ظهورك في {metrics.mentioned_count} عملية بمتوسط ترتيب {client_rank_text}."
        ),
        actions=[
            f"راجع كيف يقدّم {leader.name} منتجاته ووصفها، وحدد ما يميزك عنه بوضوح في صفحاتك.",
            "أضف محتوى يقارن بدائلك أو يبرز نقاط تفوقك (السعر، التوصيل، الجودة) بشكل صريح.",
        ],
        priority=impact * confidence,
    )


def _recommendation_gap(metrics: VisibilityMetricsV2) -> VisibilityOpportunity | None:
    if metrics.mention_rate is None or metrics.recommendation_rate is None:
        return None
    if metrics.successful_answers < MIN_SAMPLE_FOR_CONFIDENT_FINDING or metrics.mention_rate < 0.2:
        return None
    if metrics.recommendation_rate >= metrics.mention_rate * 0.5:
        return None
    impact = metrics.mention_rate - metrics.recommendation_rate
    confidence = 0.7
    return VisibilityOpportunity(
        title="يُذكر متجرك لكن نادرًا ما يُوصى به",
        reason="الذكاء الاصطناعي يعرف متجرك، لكنه لا يقدّمه غالبًا كأفضل خيار عند التوصية.",
        evidence=(
            f"ظهرت علامتك في {round(metrics.mention_rate * 100)}% من عمليات البحث، "
            f"لكن لم تُذكر كتوصية مباشرة إلا في {round(metrics.recommendation_rate * 100)}% فقط."
        ),
        actions=[
            "أضف تقييمات وآراء عملاء حقيقية ظاهرة في صفحات منتجاتك.",
            "وضّح مزايا واضحة (سرعة التوصيل، الضمان، الأسعار) في وصف المتجر والمنتجات.",
        ],
        priority=impact * confidence,
    )


def derive_top_opportunities(
    metrics: VisibilityMetricsV2, top_competitors: list[CompetitorVisibilitySummary], limit: int = 2
) -> list[VisibilityOpportunity]:
    candidates = [
        _very_low_overall_visibility(metrics),
        _citation_gap(metrics),
        _competitor_ahead_gap(metrics, top_competitors),
        _recommendation_gap(metrics),
    ]
    real = [c for c in candidates if c is not None]
    real.sort(key=lambda c: c.priority, reverse=True)
    return real[:limit]
