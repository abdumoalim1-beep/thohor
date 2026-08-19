from pydantic import BaseModel


class PreviewRecommendation(BaseModel):
    """Structured output for the PreviewReport's single recommendation
    (spec Stage 11) — exactly one opportunity, grounded only in the
    queries where the store's own visibility scan already showed it
    didn't appear. Never a technical/SEO diagnosis beyond what's
    evidenced (e.g. never 'Google can't understand your page') unless the
    given data actually supports it."""

    title: str
    reason: str
    action: str
