from app.prompts.base import PromptTemplate

VISIBILITY_QUESTION_GENERATION_PROMPT = PromptTemplate(
    name="visibility_question_generation",
    version="v1",
    schema_version="v1",
    system=(
        "أنت تُولّد أسئلة طبيعية واقعية قد يطرحها عميل حقيقي على مساعد ذكاء "
        "اصطناعي (مثل ChatGPT) عند البحث عن منتج أو خدمة يقدمها هذا المتجر "
        "— وليس كلمات بحث SEO. اكتب أسئلة بصيغة محادثة طبيعية، كما يكتبها "
        "شخص حقيقي، لا عبارات بحث مفصولة بشرطات.\n\n"
        "وزّع الأسئلة على هذه الفئات التسع بالضبط (استخدم هذه القيم "
        "الإنجليزية حرفيًا في حقل category):\n"
        "- recommendation: طلب توصية مباشرة\n"
        "- best: سؤال عن الأفضل في فئة معينة\n"
        "- comparison: مقارنة بين خيارات\n"
        "- alternatives: بدائل لعلامة تجارية معروفة\n"
        "- product_discovery: اكتشاف منتج يلبي حاجة معينة\n"
        "- local: سؤال مرتبط بموقع جغرافي محدد\n"
        "- problem_solution: مشكلة يبحث المستخدم عن حل لها\n"
        "- occasion: سؤال مرتبط بمناسبة\n"
        "- price: سؤال عن السعر أو القيمة مقابل السعر\n\n"
        "لا تذكر اسم المتجر نفسه داخل نص السؤال — هذه أسئلة عامة يطرحها "
        "عميل لا يعرف بعد بوجود هذا المتجر تحديدًا.\n\n"
        "مهم جدًا: كل سؤال يجب أن يكون مختلفًا فعليًا في المعنى والزاوية عن "
        "بقية الأسئلة — لا تُعد صياغة نفس السؤال بكلمات مختلفة (مثلاً "
        "'ما أفضل X؟' ثم 'أي X هو الأفضل؟' يُعدّان سؤالًا واحدًا مكررًا، "
        "تجنّب ذلك). نوّع بين: المنتجات المحددة، المناسبات، الميزانيات، "
        "الفئات الفرعية، والمواقع الفرعية داخل نفس المدينة.\n\n"
        "أعد كائن JSON صرف فقط — بدون Markdown، بدون ```، بدون أي نص قبله "
        "أو بعده — يطابق بالضبط:\n"
        "{\n"
        '  "questions": [\n'
        '    {"text": "...", "category": "recommendation"}\n'
        "  ]\n"
        "}\n"
        "لا تضف أي حقول أخرى."
    ),
    # Deliberately one category per call (see generate_visibility_questions'
    # per-category loop) rather than asking for all 9 at once — a single
    # big ask was confirmed live to make gpt-4o-mini silently under-deliver
    # (6 per category instead of the requested 15, well under its own
    # token budget, so a compliance gap, not a truncation one). A narrower
    # per-category ask is a much more reliable count target for this model.
    user_template=(
        "نوع النشاط: {business_type}\n"
        "التصنيفات: {categories}\n"
        "الموقع/السوق: {location}\n"
        "منافسون معروفون في نفس السوق: {competitor_names}\n\n"
        "ولّد بالضبط {count} سؤالًا طبيعيًا مختلفًا فعليًا (ليس إعادة صياغة) "
        "ضمن فئة \"{category_key}\" تحديدًا فقط — لا تُدرج أي سؤال من فئة "
        "أخرى — قد يطرحها عملاء حقيقيون متنوعون في هذا السوق على مساعد "
        "ذكاء اصطناعي وهم يبحثون عن هذا النوع من المنتجات أو الخدمات."
    ),
)
