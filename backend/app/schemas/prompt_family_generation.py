from pydantic import BaseModel, Field


class PromptFamilyResult(BaseModel):
    """Natural-language questions a real customer might ask an AI assistant
    about this intent (PRD section 19) — not keywords, not templated."""

    prompts: list[str] = Field(min_length=1)
