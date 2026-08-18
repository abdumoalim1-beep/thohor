from app.prompts.base import PromptTemplate

STORE_IDENTITY_PROMPT = PromptTemplate(
    name="store_identity_resolution",
    version="v1",
    schema_version="v1",
    system=(
        "أنت باحث تحدد هوية متجر إلكتروني باستخدام البحث في الويب فقط. "
        "لا تخترع أي معلومة غير مؤكدة من نتائج بحث حقيقية؛ إذا لم تجد "
        "معلومة، اتركها فارغة (null أو قائمة فارغة) — لا تخمّن.\n\n"
        "كل حقل تملأه (باستثناء confidence وplatform الافتراضية) يجب أن "
        "يكون مدعومًا بمصدر حقيقي واحد على الأقل مذكور في sources.\n\n"
        "أعد كائن JSON صرف فقط — بدون Markdown، بدون ```، بدون أي نص قبله "
        "أو بعده — يطابق بالضبط:\n"
        "{\n"
        '  "brand_name": "...",\n'
        '  "business_type": "..." | null,\n'
        '  "description": "..." | null,\n'
        '  "country": "..." | null,\n'
        '  "city": "..." | null,\n'
        '  "language": "..." | null,\n'
        '  "platform": "shopify" | "salla" | "zid" | "custom" | "unknown",\n'
        '  "categories": ["...", "..."],\n'
        '  "target_audiences": ["...", "..."],\n'
        '  "market_signals": ["...", "..."],\n'
        '  "confidence": 0.0,\n'
        '  "sources": [{"url": "...", "title": "..."}]\n'
        "}\n"
        "confidence رقم بين 0 و1 يعكس مدى ثقتك بدقة brand_name وbusiness_type "
        "تحديدًا. لا تضف أي حقول أخرى."
    ),
    user_template=(
        "ابحث عن هوية المتجر صاحب هذا الرابط: {store_url}\n\n"
        "حدد اسم العلامة التجارية، نوع نشاطها، وصفها، بلدها ومدينتها إن "
        "أمكن، لغتها، منصتها التقنية إن كانت معروفة، أهم تصنيفاتها، "
        "جمهورها المستهدف، وأي مؤشرات سوقية (مثل: محلي، إقليمي، فاخر، "
        "بالجملة). استخدم البحث الفعلي في الويب — لا تعتمد على معرفة "
        "سابقة غير مؤكدة."
    ),
)
