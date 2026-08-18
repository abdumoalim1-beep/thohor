import json
import uuid

from sqlmodel import Session, select

from app.models.catalog import Page, PageSnapshot
from app.models.recommendation import Recommendation
from app.opportunities.evidence_trace import trace_recommendation_evidence
from app.providers.ai.base import AIMessage, AIRole
from app.providers.ai.router import ModelRouter
from app.schemas.implementation_execution import OnDemandImplementationOutput


def _latest_target_snapshot(session: Session, recommendation: Recommendation) -> PageSnapshot | None:
    if not recommendation.target_page:
        return None
    page = session.exec(
        select(Page)
        .where(Page.store_id == recommendation.store_id)
        .where(Page.url == recommendation.target_page)
    ).first()
    if page is None:
        return None
    return session.exec(
        select(PageSnapshot)
        .where(PageSnapshot.page_id == page.id)
        .order_by(PageSnapshot.observed_at.desc())  # type: ignore[arg-type]
    ).first()


def build_execution_context(session: Session, recommendation: Recommendation, mode: str) -> dict:
    trace = trace_recommendation_evidence(session, recommendation.id)
    snapshot = _latest_target_snapshot(session, recommendation)
    evidence = [] if trace is None else [
        {"source_type": item.source_type.value, "summary": item.summary, "confidence": item.confidence}
        for item in trace["evidence"]
    ]
    findings = [] if trace is None else [
        {"statement": item.statement, "confidence": item.confidence, "status": item.status.value}
        for item in trace["findings"]
    ]
    return {
        "mode": mode,
        "recommendation": {
            "title": recommendation.title,
            "what_we_found": recommendation.what_we_found,
            "what_to_do": recommendation.what_to_do,
            "why_it_matters": recommendation.why_it_matters,
            "target_page": recommendation.target_page,
            "target_intents": recommendation.target_intents,
            "implementation_steps": recommendation.implementation_steps,
            "existing_package": recommendation.implementation_package,
        },
        "current_page": None if snapshot is None else {
            "title": snapshot.title,
            "h1": snapshot.h1,
            "links": snapshot.links,
            "entities": snapshot.entities,
        },
        "findings": findings,
        "evidence": evidence,
    }


async def generate_on_demand_implementation(
    session: Session,
    router: ModelRouter,
    recommendation: Recommendation,
    mode: str,
    research_run_id: uuid.UUID | None = None,
) -> tuple[OnDemandImplementationOutput, uuid.UUID]:
    context = build_execution_context(session, recommendation, mode)
    task_type = "page_rebuild_generation" if mode == "rebuild" else "article_draft_generation"
    instruction = (
        "أعد اقتراح إعادة بناء للصفحة الحالية مع مقارنة current/proposed لكل عنصر."
        if mode == "rebuild"
        else "أعد مسودة صفحة أو مقالة تغطي النوايا والأدلة المتاحة."
    )
    messages = [
        AIMessage(
            role=AIRole.system,
            content=(
                "أنت منفذ محتوى عربي لمتاجر إلكترونية. أعد JSON مطابقًا للمخطط فقط. "
                "استخدم الحقائق الموجودة في السياق حصراً. لا تختلق أسعارًا أو منتجات أو جمهورًا أو Search Volume أو KD أو CPC. "
                "ضع أي معلومة لازمة وغير مؤكدة في assumptions_requiring_confirmation. "
                "اجعل reasons مرتبطة بالدليل أو صرّح بأنها أفضل ممارسة عامة."
            ),
        ),
        AIMessage(role=AIRole.user, content=f"{instruction}\n\nالسياق:\n{json.dumps(context, ensure_ascii=False, default=str)}"),
    ]
    response = await router.execute(
        session=session,
        task_type=task_type,
        messages=messages,
        research_run_id=research_run_id or recommendation.last_seen_research_run_id,
        prompt_name="on_demand_implementation",
        prompt_version="v1",
        schema_version="v1",
        response_schema=OnDemandImplementationOutput,
        max_tokens=4000,
        temperature=0.2,
        use_cache=True,
    )
    if response.execution_id is None or response.parsed is None:
        raise RuntimeError("implementation generation returned no persisted output")
    return OnDemandImplementationOutput.model_validate(response.parsed), response.execution_id
