from pydantic import BaseModel, Field

from app.models.intent import CommercialStage, DemandLevel


class IntentSuggestion(BaseModel):
    topic: str
    category: str | None = None
    commercial_stage: CommercialStage
    estimated_demand: DemandLevel
    keywords: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class IntentExpansionResult(BaseModel):
    intents: list[IntentSuggestion] = Field(default_factory=list)
