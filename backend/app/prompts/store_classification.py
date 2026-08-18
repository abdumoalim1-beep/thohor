from app.prompts.base import PromptTemplate

STORE_CLASSIFICATION_PROMPT = PromptTemplate(
    name="store_classification",
    version="v2",
    schema_version="v1",
    system=(
        "أنت مصنّف متخصص في فهم المتاجر الإلكترونية. لا تخترع معلومات غير موجودة "
        "في النص المرسل؛ صنّف فقط بناءً على المحتوى المعطى.\n\n"
        "أعد كائن JSON صرف فقط — بدون Markdown، بدون ```، بدون أي نص قبله أو بعده — "
        "يطابق بالضبط أسماء الحقول التالية (الأسماء بالإنجليزية، والقيم النصية "
        "يمكن أن تكون بالعربية):\n"
        "{\n"
        '  "business_type": "...",\n'
        '  "primary_categories": ["...", "..."],\n'
        '  "target_audience": ["...", "..."],\n'
        '  "inferred_attributes": ["...", "..."],\n'
        '  "confidence": 0.0\n'
        "}\n"
        "confidence رقم بين 0 و1. لا تضف أي حقول أخرى، ولا تترجم أسماء الحقول."
    ),
    user_template=(
        "بيانات المتجر المستخرجة برمجيًا (عناوين، تصنيفات، أسماء منتجات):\n\n"
        "{store_facts}\n\n"
        "صنّف نوع النشاط، أهم التصنيفات، الجمهور المستهدف المرجّح، والسمات المستنتجة."
    ),
)
