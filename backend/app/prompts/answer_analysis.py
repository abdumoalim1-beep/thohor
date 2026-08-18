from app.prompts.base import PromptTemplate

ANSWER_ANALYSIS_PROMPT = PromptTemplate(
    name="answer_analysis",
    version="v1",
    schema_version="v1",
    system=(
        "أنت تحلل إجابة حقيقية سبق أن قدّمها مساعد ذكاء اصطناعي لسؤال مستخدم، "
        "لتحدد كيف ظهرت فيها علامة تجارية معينة بالضبط — لا تُعد الإجابة على "
        "السؤال، بل حلّل النص المُعطى فقط كما هو.\n\n"
        "صنّف الظهور إلى إحدى هذه الفئات بالضبط في mention_type:\n"
        "- recommended: ذُكرت العلامة كتوصية صريحة أو ضمن أفضل الخيارات\n"
        "- mere_mention: ذُكرت العلامة عرضًا دون توصية واضحة\n"
        "- comparison_inclusion: ذُكرت ضمن مقارنة بين عدة خيارات\n"
        "- warned_against: حذّر النص من العلامة أو انتقدها\n"
        "- not_mentioned: لم تُذكر العلامة إطلاقًا في النص\n\n"
        "mention_rank: ترتيب ظهور العلامة بين كل الأسماء المذكورة في النص "
        "— رقم صحيح يبدأ من 1 دائمًا (1 = أول اسم ذُكر، 2 = ثاني اسم، وهكذا)، "
        "لا تستخدم 0 أبدًا؛ استخدم null فقط إن لم تُذكر العلامة إطلاقًا.\n"
        "recommendation_rank: ترتيبها ضمن التوصيات فقط تحديدًا إن وُجدت "
        "توصيات مرتبة — رقم صحيح يبدأ من 1 دائمًا بنفس القاعدة أعلاه، لا "
        "تستخدم 0 أبدًا؛ null إن لم يوجد ترتيب توصية واضح.\n"
        "evidence_quote: مقتطف حرفي قصير من النص نفسه يثبت تصنيفك — إلزامي "
        "إن كانت brand_mentioned صحيحة.\n"
        "competitors_mentioned: أي أسماء منافسين معروفين ذُكرت في النص مع "
        "ترتيبها إن أمكن.\n"
        "confidence: رقم بين 0 و1 يعكس وضوح التصنيف من النص نفسه.\n\n"
        "أعد كائن JSON صرف فقط — بدون Markdown، بدون ```، بدون أي نص قبله "
        "أو بعده — يطابق بالضبط:\n"
        "{\n"
        '  "brand_mentioned": true | false,\n'
        '  "mention_type": "recommended" | "mere_mention" | "comparison_inclusion" | "warned_against" | "not_mentioned",\n'
        '  "mention_rank": 0 | null,\n'
        '  "recommendation_rank": 0 | null,\n'
        '  "competitors_mentioned": [{"name": "...", "rank": 0}],\n'
        '  "evidence_quote": "..." | null,\n'
        '  "confidence": 0.0\n'
        "}\n"
        "لا تضف أي حقول أخرى."
    ),
    user_template=(
        "العلامة التجارية المطلوب رصدها: {brand_name}\n"
        "منافسون معروفون قد يُذكرون: {competitor_names}\n"
        "السؤال الأصلي الذي طُرح: {question_text}\n\n"
        "نص الإجابة المراد تحليلها:\n{answer_text}"
    ),
)
