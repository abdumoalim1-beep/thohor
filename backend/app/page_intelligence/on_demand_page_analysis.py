import json

from app.crawler.extract import PageFacts
from app.providers.ai.base import AIMessage, AIRole


def public_page_facts(facts: PageFacts) -> dict:
    return {
        "url": facts.url,
        "title": facts.title,
        "h1": facts.h1,
        "meta_description": facts.meta_description,
        "headings_or_entities": [
            item.get("name") for item in facts.json_ld[:10]
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ],
        "internal_links_count": len(facts.internal_links),
        "body_excerpt": facts.body_text[:6000],
    }


def winning_page_messages(query: str, competitor: PageFacts, target: PageFacts | None) -> list[AIMessage]:
    payload = {
        "query": query,
        "winning_page": public_page_facts(competitor),
        "store_page": public_page_facts(target) if target else None,
    }
    return [
        AIMessage(role=AIRole.system, content=(
            "أنت محلل صفحات تجارة إلكترونية. حلل فقط ما يظهر في الحقائق المرفقة وأعد JSON مطابقًا للمخطط. "
            "لا تدّع أن عاملًا ما سبب الترتيب؛ استخدم صيغة إشارات محتملة مرتبطة بما رُصد. "
            "لا تختلق Search Volume أو KD أو CPC أو جمهورًا أو خصائص منتجات. "
            "إذا لم توجد صفحة للمتجر فاعتبرها فجوة صفحة، ولا تخترع محتواها الحالي. "
            "أعد كائن JSON فقط بهذه الحقول الإلزامية حرفيًا: "
            "summary نص، why_this_page_wins قائمة نصوص، gaps قائمة نصوص، changes قائمة كائنات، "
            "content_sections قائمة نصوص، assumptions_requiring_confirmation قائمة نصوص. "
            "كل عنصر في changes يجب أن يحتوي حرفيًا على: area، competitor_observation، "
            "store_observation (نص أو null)، recommended_change، evidence_basis. "
            "لا تعد كائن الإدخال ولا تضف غلافًا مثل query أو winning_page."
        )),
        AIMessage(role=AIRole.user, content=json.dumps(payload, ensure_ascii=False)),
    ]
