from pydantic import BaseModel, Field

# The 9-category taxonomy of natural buyer questions this generates for —
# distinct from Intent/PromptFamily's SEO-keyword shape (Phase 5 plan).
QUESTION_CATEGORIES = frozenset({
    "recommendation", "best", "comparison", "alternatives", "product_discovery",
    "local", "problem_solution", "occasion", "price",
})


class GeneratedQuestion(BaseModel):
    text: str
    category: str


class QuestionGenerationResult(BaseModel):
    questions: list[GeneratedQuestion] = Field(default_factory=list)
