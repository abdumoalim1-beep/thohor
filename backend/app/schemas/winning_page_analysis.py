from pydantic import BaseModel, Field, HttpUrl


class WinningPageAnalysisRequest(BaseModel):
    market_research_run_id: str
    query: str = Field(min_length=2, max_length=200)
    competitor_url: HttpUrl
    target_url: HttpUrl | None = None


class WinningPageChange(BaseModel):
    area: str
    competitor_observation: str
    store_observation: str | None = None
    recommended_change: str
    evidence_basis: str


class WinningPageAnalysisOutput(BaseModel):
    summary: str
    why_this_page_wins: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    changes: list[WinningPageChange] = Field(default_factory=list)
    content_sections: list[str] = Field(default_factory=list)
    assumptions_requiring_confirmation: list[str] = Field(default_factory=list)


class WinningPageAnalysisResponse(BaseModel):
    research_run_id: str
    status: str
    query: str
    competitor_url: str
    target_url: str | None = None
    competitor_facts: dict
    target_facts: dict | None = None
    output: WinningPageAnalysisOutput
    ai_execution_id: str
    ai_cost_usd: float | None = None


class ConvertWinningPageAnalysisResponse(BaseModel):
    opportunity_id: str
    recommendation_id: str
    recommendation_title: str
