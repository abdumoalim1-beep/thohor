from pydantic import BaseModel, Field


class PageGapAnalysisResult(BaseModel):
    gaps: list[str] = Field(min_length=1)
    recommendation_summary: str
    confidence: float = Field(ge=0.0, le=1.0)
