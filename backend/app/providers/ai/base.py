import uuid
from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel, Field


class AIRole(str, Enum):
    system = "system"
    user = "user"


class AIMessage(BaseModel):
    role: AIRole
    content: str


class AIRequest(BaseModel):
    task_type: str
    model: str
    messages: list[AIMessage]
    max_tokens: int | None = None
    temperature: float = 0.0
    prompt_name: str | None = None
    prompt_version: str | None = None
    # A single provider-agnostic switch, not OpenAI's raw `tools` schema —
    # each provider decides internally how (or whether) to satisfy this.
    # Providers that can't must raise AIProviderError, never silently ignore it.
    enable_web_search: bool = False


class AIUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class AIResponse(BaseModel):
    provider: str
    model: str
    text: str
    parsed: dict | None = None
    usage: AIUsage = Field(default_factory=AIUsage)
    latency_ms: int = 0
    raw: dict | None = None
    # Populated by ModelRouter after logging to ai_executions — lets callers
    # attach Evidence rows to the exact execution that produced this output.
    execution_id: uuid.UUID | None = None
    # Set by the provider, never assumed by the caller — lets a consumer
    # tell whether a web_search request actually ran a search vs. silently
    # fell back to a plain generation.
    web_search_used: bool = False
    sources: list[dict] | None = None


class AIProviderError(RuntimeError):
    pass


class AIProvider(ABC):
    """Unified interface every model adapter implements. Business logic must
    never call a provider SDK directly — always go through this interface
    (and in practice through ModelRouter.execute, not a raw provider)."""

    name: str

    @abstractmethod
    async def generate(self, request: AIRequest) -> AIResponse: ...
