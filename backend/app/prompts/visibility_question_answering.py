from app.prompts.base import PromptTemplate

# Deliberately minimal — the whole point is capturing what the engine would
# actually say to a real user asking this question, not a specially-primed
# answer. No mention of "test"/"evaluation"/the store being measured.
VISIBILITY_QUESTION_ANSWERING_PROMPT = PromptTemplate(
    name="visibility_question_answering",
    version="v1",
    schema_version="v1",
    system=(
        "أجب على سؤال المستخدم التالي كما تجيب عادةً — بأسلوبك الطبيعي "
        "المعتاد، بنفس لغة السؤال، دون أي تعليق إضافي عن طبيعة هذا الطلب."
    ),
    user_template="{question}",
)
