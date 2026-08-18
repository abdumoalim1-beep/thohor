from pydantic import BaseModel, Field


class StoreClassification(BaseModel):
    """Structured output for the store-understanding AI enrichment step
    (PRD section 12). This is enrichment, not fact: business_type/audience/
    attributes are the model's classification of programmatically-extracted
    content, always traceable to the ai_executions row that produced them.
    """

    business_type: str
    primary_categories: list[str] = Field(default_factory=list)
    target_audience: list[str] = Field(default_factory=list)
    inferred_attributes: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
