from pydantic import BaseModel, Field


class OnDemandAnalysisHistoryItem(BaseModel):
    research_run_id: str
    kind: str
    status: str
    topic: str
    summary: str | None = None
    created_at: str
    completed_at: str | None = None
    serp_cost_usd: float = 0.0
    ai_cost_usd: float = 0.0
    recommendation_id: str | None = None
    recommendation_title: str | None = None


class OnDemandAnalysisHistoryResponse(BaseModel):
    analyses: list[OnDemandAnalysisHistoryItem] = Field(default_factory=list)

