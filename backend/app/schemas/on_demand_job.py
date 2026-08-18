from typing import Any, Literal

from pydantic import BaseModel


class OnDemandJobResponse(BaseModel):
    research_run_id: str
    kind: Literal["market_exploration", "winning_page_analysis", "implementation_generation"]
    status: Literal["pending", "running", "completed", "failed", "cancelled"]


class OnDemandJobStatus(OnDemandJobResponse):
    error: str | None = None
    result: dict[str, Any] | None = None

