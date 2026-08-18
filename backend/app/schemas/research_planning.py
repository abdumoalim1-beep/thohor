from pydantic import BaseModel, Field

from app.models.research_task import TaskType


class NewTaskSuggestion(BaseModel):
    task_type: TaskType
    target: str
    reason: str
    hypothesis: str | None = None
    priority: float = Field(ge=0.0, le=1.0)


class ResearchPlanResult(BaseModel):
    new_tasks: list[NewTaskSuggestion] = Field(default_factory=list)
