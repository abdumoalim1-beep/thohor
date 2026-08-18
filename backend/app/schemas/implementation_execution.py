from typing import Literal

from pydantic import BaseModel, Field


class PageChange(BaseModel):
    field: str
    current: str | None = None
    proposed: str
    reason: str


class OnDemandImplementationOutput(BaseModel):
    summary: str
    changes: list[PageChange] = Field(default_factory=list)
    title: str | None = None
    meta_description: str | None = None
    h1: str | None = None
    h2_sections: list[str] = Field(default_factory=list)
    faq: list[str] = Field(default_factory=list)
    internal_links: list[str] = Field(default_factory=list)
    draft: str | None = None
    developer_instructions: list[str] = Field(default_factory=list)
    content_instructions: list[str] = Field(default_factory=list)
    assumptions_requiring_confirmation: list[str] = Field(default_factory=list)


class GenerateImplementationRequest(BaseModel):
    mode: Literal["rebuild", "article"]


class GenerateImplementationResponse(BaseModel):
    mode: Literal["rebuild", "article"]
    status: Literal["completed"] = "completed"
    output: OnDemandImplementationOutput
    ai_execution_id: str
    cost_usd: float | None = None

