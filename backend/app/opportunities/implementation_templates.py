import uuid
from dataclasses import dataclass, field
from typing import Callable

from sqlmodel import Session

from app.models.opportunity import Opportunity
from app.models.stable_intent import StableIntent


@dataclass
class RecommendationContent:
    title: str
    # Beta Readiness Remediation, Section 5 structure. what_we_found must
    # only ever restate what the attached evidence actually shows (never a
    # claim the evidence doesn't support); why_this_improvement is the
    # explicit reasoning link between what_we_found and what_to_do — never
    # silently assumed. claim_basis records whether what_to_do's specific
    # implementation detail is itself evidence-derived or general best
    # practice (Section 4) — every current template's implementation_steps
    # are best-practice specifics applied to an evidence-confirmed gap, so
    # "observed_with_best_practice" is the honest default throughout; no
    # template invents a number/statistic that isn't in the evidence.
    what_we_found: str
    what_to_do: str
    why_it_matters: str
    why_this_improvement: str
    claim_basis: str = "observed_with_best_practice"
    implementation_steps: list[str] = field(default_factory=list)
    measurement_plan: dict = field(default_factory=dict)
    implementation_package: dict = field(default_factory=dict)


def _measurement_contract(
    opportunity: Opportunity,
    *,
    target_surfaces: list[str],
    expected_direction: str,
    success_metric: str,
    duration_weeks: int,
) -> dict:
    """Beta Readiness Remediation, Section 13 — every measurable
    recommendation carries an explicit contract: what we'll re-measure
    (target_intents/target_surfaces), what "before" means
    (baseline_reference — the real MeasurementBaseline row captured at
    creation time via app.measurement.baseline, never re-described here),
    which direction would count as improvement, the window we'll wait
    before judging, and the concrete metric app.measurement.outcome's
    classify_outcome() actually reads. No promise of a guaranteed result —
    only what will be observed and how it will be judged."""
    return {
        "target_intents": opportunity.affected_intents,
        "target_surfaces": target_surfaces,
        "baseline_reference": "measurement_baselines row captured when this recommendation was first created",
        "expected_direction": expected_direction,
        "duration_weeks": duration_weeks,
        "success_metric": success_metric,
    }


def _intent_topics(session: Session, stable_intent_ids: list[str]) -> list[str]:
    """opportunity.affected_intents holds StableIntent ids (Part F.5-0) —
    resolving through the stable identity, not the run-scoped Intent row,
    keeps recommendation copy meaningful even long after the research_run
    that created it."""
    topics = []
    for stable_intent_id in stable_intent_ids:
        stable_intent = session.get(StableIntent, uuid.UUID(stable_intent_id))
        if stable_intent is not None:
            topics.append(stable_intent.canonical_topic)
    return topics


def _build_missing_landing_page(opportunity: Opportunity, session: Session) -> RecommendationContent:
    topics = _intent_topics(session, opportunity.affected_intents)
    topic = topics[0] if topics else opportunity.title
    return RecommendationContent(
        title=f"أنشئ صفحة مخصصة لـ '{topic}'",
        what_we_found=opportunity.description,
        what_to_do=f"أنشئ صفحة/landing page مخصصة تستهدف نية '{topic}' مباشرة، بمحتوى فعلي وليس صفحة تحويل فقط.",
        why_it_matters=f"منافس حقيقي يغطي هذه النية بمحتوى فعلي حاليًا، بينما كتالوجك لا يقدّم صفحة مخصصة لها — عملاء يبحثون عن '{topic}' قد يصلون لصفحة المنافس بدلاً من صفحتك.",
        why_this_improvement="التوصية مبنية مباشرة على مقارنة فعلية مع صفحة منافس حقيقية زُحفت واستُخرجت عناصرها المفقودة تحديدًا (راجع WHAT WE FOUND) — وليست نصيحة SEO عامة.",
        claim_basis="observed_with_best_practice",
        implementation_steps=[
            "أنشئ الصفحة بعنوان ورابط يعكسان النية بوضوح",
            "أضف مقدمة تشرح ما يقدمه المتجر لهذه الحاجة تحديدًا",
            "اربط المنتجات/التصنيفات ذات الصلة",
            "أضف قسم أسئلة شائعة (FAQ)",
            "أضف Internal Links من الصفحات ذات الصلة",
            "أضف Structured Data المناسب (Product/FAQPage حسب المحتوى)",
        ],
        measurement_plan=_measurement_contract(
            opportunity,
            target_surfaces=["google"],
            expected_direction="client_rank يظهر (كان None) أو ينخفض رقميًا",
            success_metric="client_rank <= 10 لنفس النية بعد التنفيذ",
            duration_weeks=4,
        ),
        implementation_package={
            "suggested_title": f"{topic} | دليل شامل",
            "suggested_meta_description": f"كل ما تحتاج معرفته عن {topic}.",
            "h1": topic,
            "suggested_h2_sections": ["نظرة عامة", "الخيارات المتاحة", "كيف تختار المناسب لك", "أسئلة شائعة"],
            "faq_questions": [f"ما هو {topic}؟", f"كيف أختار {topic} المناسب؟"],
            "schema_suggestions": ["Product", "FAQPage", "BreadcrumbList"],
            "internal_links": [],
            "content_outline": ["مقدمة", "الخيارات", "المقارنة", "التوصية", "الأسئلة الشائعة"],
            "suggested_copy": "",
            "urls_affected": [],
            "developer_instructions": "أنشئ route/صفحة جديدة وفق بنية المتجر الحالية مع structured data المذكورة.",
            "content_writer_instructions": "اكتب محتوى أصلي يجيب فعليًا عن نية العميل، وليس نصًا تسويقيًا عامًا.",
        },
    )


def _build_google_visibility_gap(opportunity: Opportunity, session: Session) -> RecommendationContent:
    topics = _intent_topics(session, opportunity.affected_intents)
    topic = topics[0] if topics else opportunity.title
    has_target_page = bool(opportunity.affected_pages)
    page_note = (
        "راجع الصفحة الأقرب لهذه النية في كتالوجك"
        if not has_target_page
        else "راجع الصفحة المرتبطة بهذه النية"
    )
    return RecommendationContent(
        title=f"حسّن ظهورك في Google لـ '{topic}'",
        what_we_found=opportunity.description,
        what_to_do=f"{page_note} وحسّن العنوان/الوصف/المحتوى ليطابق ما يبحث عنه العملاء فعليًا لنية '{topic}'.",
        why_it_matters="عملاء يبحثون عن هذه النية على Google لن يجدوا متجرك ضمن أول 10 نتائج، وهو النطاق الذي يحصل على الغالبية العظمى من النقرات.",
        why_this_improvement=(
            "لم نحدد بعد صفحة معينة في كتالوجك تستهدف هذه النية مباشرة — راجع أقرب صفحة لديك يدويًا قبل التنفيذ."
            if not has_target_page
            else "التحسينات المقترحة عامة (عنوان/وصف/H1) لأننا لم نقارن صفحتك بمنافس محدد لهذه النية بعد."
        ),
        claim_basis="observed_with_best_practice",
        implementation_steps=[
            "راجع العنوان (title) والوصف (meta description) للصفحة الأقرب لهذه النية",
            "تأكد أن H1 يعكس النية بوضوح",
            "أضف محتوى يجيب مباشرة عن سؤال العميل",
            "تحقق من وجود Structured Data صحيح",
        ],
        measurement_plan=_measurement_contract(
            opportunity,
            target_surfaces=["google"],
            expected_direction="client_rank ينخفض رقميًا نحو أفضل 10 نتائج",
            success_metric="client_rank <= 10 لنفس النية بعد التنفيذ",
            duration_weeks=4,
        ),
        implementation_package={
            "suggested_title": topic,
            "suggested_meta_description": f"{topic} — تسوّق الآن.",
            "h1": topic,
            "suggested_h2_sections": [],
            "faq_questions": [],
            "schema_suggestions": ["Product"],
            "internal_links": [],
            "content_outline": [],
            "suggested_copy": "",
            "urls_affected": opportunity.affected_pages,
            "developer_instructions": "",
            "content_writer_instructions": f"حسّن نص الصفحة ليغطي '{topic}' بوضوح أكبر.",
        },
    )


def _build_ai_citation_gap(opportunity: Opportunity, session: Session) -> RecommendationContent:
    topics = _intent_topics(session, opportunity.affected_intents)
    topic = topics[0] if topics else opportunity.title
    return RecommendationContent(
        title=f"اجعل متجرك يُذكر في إجابات AI عن '{topic}'",
        what_we_found=opportunity.description,
        what_to_do="وضّح هوية العلامة التجارية والمنتج بمحتوى صريح ومنظم (Schema + نص واضح) ليسهل على مساعدات AI فهمه واقتباسه.",
        why_it_matters="عملاء يسألون مساعدات AI (مثل ChatGPT) عن هذه النية قد يحصلون على اسم منافس بدل متجرك، لأن المتجر لم يُذكر في أي من محاولات القياس بينما مُنافس ذُكر.",
        why_this_improvement="لا نملك دليلًا مباشرًا يثبت أن إضافة Schema بعينها سترفع نسبة الذكر — هذه ممارسة شائعة تُسهّل على نماذج AI فهم هوية العلامة، وليست ضمانًا مبنيًا على تجربة سابقة لهذا المتجر تحديدًا.",
        claim_basis="observed_with_best_practice",
        implementation_steps=[
            "أضف/حدّث Organization و Brand schema بوضوح",
            "أضف صفحة 'من نحن' أو محتوى يوضح هوية العلامة",
            "أضف محتوى مقارنة/توصية واضح لهذه النية",
        ],
        measurement_plan=_measurement_contract(
            opportunity,
            target_surfaces=["ai_chatgpt"],
            expected_direction="mentioned يتحول من False إلى True في محاولات لاحقة",
            success_metric="mentioned = true لنفس النية عبر تكرارات القياس التالية",
            duration_weeks=6,
        ),
        implementation_package={
            "suggested_title": "",
            "suggested_meta_description": "",
            "h1": "",
            "suggested_h2_sections": [],
            "faq_questions": [f"من يقدم {topic}؟"],
            "schema_suggestions": ["Organization", "Brand"],
            "internal_links": [],
            "content_outline": [],
            "suggested_copy": "",
            "urls_affected": [],
            "developer_instructions": "أضف JSON-LD Organization/Brand في الصفحات الرئيسية إن لم تكن موجودة.",
            "content_writer_instructions": f"اكتب محتوى واضح يوضح لماذا المتجر خيار موثوق لـ'{topic}'.",
        },
    )


def _build_category_visibility_gap(opportunity: Opportunity, session: Session) -> RecommendationContent:
    return RecommendationContent(
        title=f"راجع استراتيجية التصنيف: {opportunity.title}",
        what_we_found=opportunity.description,
        what_to_do=opportunity.description + " — راجع صفحات هذا التصنيف ككل بدل نية واحدة فقط.",
        why_it_matters="ضعف ظهور متكرر عبر عدة نوايا في نفس التصنيف يشير لمشكلة بنيوية في صفحة التصنيف نفسها، وليس مجرد صفحة منتج واحدة.",
        why_this_improvement="القياس مبني فقط على النوايا التي قِيست فعليًا هذا التشغيل (وليس كل نوايا التصنيف) — راجع WHAT WE FOUND للعدد الدقيق.",
        claim_basis="observed_with_best_practice",
        implementation_steps=[
            "راجع صفحة التصنيف الرئيسية وبنيتها",
            "تأكد من وجود محتوى وصفي كافٍ لكل نية فرعية",
            "أضف Internal Linking بين صفحات التصنيف",
        ],
        measurement_plan=_measurement_contract(
            opportunity,
            target_surfaces=["google"],
            expected_direction="نسبة تغطية التصنيف (نوايا ظاهرة/إجمالي المقاسة) ترتفع",
            success_metric="coverage >= 0.34 (نفس عتبة CATEGORY_COVERAGE_FLOOR) بعد التنفيذ",
            duration_weeks=6,
        ),
        implementation_package={
            "suggested_title": "",
            "suggested_meta_description": "",
            "h1": "",
            "suggested_h2_sections": [],
            "faq_questions": [],
            "schema_suggestions": ["CollectionPage"],
            "internal_links": [],
            "content_outline": [],
            "suggested_copy": "",
            "urls_affected": [],
            "developer_instructions": "",
            "content_writer_instructions": "",
        },
    )


def _build_page_rebuild_gap(opportunity: Opportunity, session: Session) -> RecommendationContent:
    analysis = opportunity.score_breakdown.get("analysis") or {}
    changes = analysis.get("changes") or []
    sections = analysis.get("content_sections") or []
    gaps = analysis.get("gaps") or []
    query = (opportunity.affected_queries or [opportunity.title])[0]
    target = opportunity.affected_pages[0] if opportunity.affected_pages else None
    return RecommendationContent(
        title=(f"أعد بناء صفحة '{query}'" if target else f"أنشئ صفحة مخصصة لـ '{query}'"),
        what_we_found=opportunity.description,
        what_to_do=("طبّق التغييرات المحددة على الصفحة المرتبطة." if target else "أنشئ صفحة جديدة تغطي الموضوع والفجوات المرصودة."),
        why_it_matters="المقارنة عند الطلب وجدت فروقًا محددة بين صفحة متصدرة وما يقدمه المتجر لهذا الموضوع.",
        why_this_improvement="كل تغيير في الحزمة أدناه مرتبط بعنصر زُحف من الصفحة المتصدرة أو بغياب عنصر مقابل في صفحة المتجر؛ وهي إشارات مقارنة وليست ضمانًا للترتيب.",
        claim_basis="observed_with_best_practice",
        implementation_steps=[change.get("recommended_change", "") for change in changes if change.get("recommended_change")]
        or ["راجع الفجوات المرصودة وابنِ الصفحة لتغطيتها بوضوح"],
        measurement_plan=_measurement_contract(
            opportunity, target_surfaces=["google"], expected_direction="تحسن ترتيب المتجر للاستعلام المختار",
            success_metric="client_rank يتحسن في إعادة القياس التالية", duration_weeks=4,
        ),
        implementation_package={
            "suggested_title": next((c.get("recommended_change") for c in changes if str(c.get("area", "")).lower() in {"title", "seo title"}), ""),
            "suggested_meta_description": next((c.get("recommended_change") for c in changes if "meta" in str(c.get("area", "")).lower()), ""),
            "h1": next((c.get("recommended_change") for c in changes if str(c.get("area", "")).lower() == "h1"), ""),
            "suggested_h2_sections": sections,
            "faq_questions": [],
            "schema_suggestions": [],
            "internal_links": [],
            "content_outline": sections,
            "suggested_copy": "",
            "urls_affected": opportunity.affected_pages,
            "developer_instructions": "نفّذ التغييرات بعد مراجعتها ولا تنشر آليًا.",
            "content_writer_instructions": "غطِ الفجوات المرصودة فقط وتحقق من أي افتراض قبل النشر.",
            "comparison_changes": changes,
            "observed_gaps": gaps,
        },
    )


def _build_generic(opportunity: Opportunity, session: Session) -> RecommendationContent:
    """Fallback for any opportunity_type without a bespoke template yet —
    keeps the extensible detector registry (Group E1) end-to-end usable: a
    new detector type never breaks recommendation generation, it just gets
    a plainer template until a dedicated one is written."""
    return RecommendationContent(
        title=opportunity.title,
        what_we_found=opportunity.description,
        what_to_do=opportunity.description,
        why_it_matters=opportunity.description,
        why_this_improvement="فرصة من نوع جديد بلا قالب مخصص بعد — راجع التفاصيل يدويًا قبل التنفيذ.",
        claim_basis="unsupported",
        implementation_steps=["راجع تفاصيل هذه الفرصة واتخذ إجراءً مناسبًا"],
        measurement_plan={"target_intents": opportunity.affected_intents, "duration_weeks": 4},
        implementation_package={},
    )


RECOMMENDATION_TEMPLATES: dict[str, Callable[[Opportunity, Session], RecommendationContent]] = {
    "missing_landing_page": _build_missing_landing_page,
    "google_visibility_gap": _build_google_visibility_gap,
    "ai_citation_gap": _build_ai_citation_gap,
    "category_visibility_gap": _build_category_visibility_gap,
    "page_rebuild_gap": _build_page_rebuild_gap,
}


def build_recommendation_content(opportunity: Opportunity, session: Session) -> RecommendationContent:
    template = RECOMMENDATION_TEMPLATES.get(opportunity.opportunity_type, _build_generic)
    return template(opportunity, session)
