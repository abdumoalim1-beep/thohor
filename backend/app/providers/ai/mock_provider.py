import json

from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage


class MockAIProvider(AIProvider):
    """Deterministic, network-free provider for unit tests and CI. Never
    used for real research runs — the router only selects this provider
    when explicitly wired in tests."""

    name = "mock"

    async def generate(self, request: AIRequest) -> AIResponse:
        text = json.dumps({"mock": True, "task_type": request.task_type})
        return AIResponse(
            provider=self.name,
            model=request.model,
            text=text,
            usage=AIUsage(input_tokens=10, output_tokens=10),
            latency_ms=1,
            raw={"mock": True},
        )
