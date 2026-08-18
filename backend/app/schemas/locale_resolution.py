from pydantic import BaseModel, Field


class LocaleGuess(BaseModel):
    """Last-resort AI fallback output for app.crawler.locale_detection —
    only ever consulted when the deterministic signal pass is inconclusive.
    """

    country: str
    language: str
    confidence: float = Field(ge=0.0, le=1.0)
