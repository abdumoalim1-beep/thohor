import time

import anthropic
from anthropic import AsyncAnthropic

from app.core.retry import RetryExhaustedError, retry_with_backoff
from app.providers.ai.base import AIProvider, AIProviderError, AIRequest, AIResponse, AIRole, AIUsage

# Part H5 — SDK default retrying disabled (max_retries=0) in favor of our
# uniform retry_with_backoff, same rationale as openai_provider.py.
# OverloadedError (HTTP 529, Anthropic-specific "temporarily over capacity")
# is retryable — it is not a client mistake, unlike RateLimitError's cousin
# rate-limit-forever case which retrying can't fix either way within 3 tries.
_RETRYABLE_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
    anthropic.OverloadedError,
)


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, _RETRYABLE_EXCEPTIONS)


def _is_rate_limit(exc: Exception) -> bool:
    return isinstance(exc, (anthropic.RateLimitError, anthropic.OverloadedError))


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key: str):
        self._client = AsyncAnthropic(api_key=api_key, max_retries=0)

    async def generate(self, request: AIRequest) -> AIResponse:
        if request.enable_web_search:
            # Anthropic's web_search_20250305 tool isn't wired up yet
            # (planned for the multi-engine visibility phase) — fail loudly
            # rather than silently answering from training data only.
            raise AIProviderError("anthropic provider does not yet support enable_web_search")
        start = time.monotonic()
        system_prompt = "\n".join(m.content for m in request.messages if m.role == AIRole.system) or None
        user_messages = [
            {"role": "user", "content": m.content} for m in request.messages if m.role != AIRole.system
        ]

        async def _do_request():
            return await self._client.messages.create(
                model=request.model,
                system=system_prompt,
                messages=user_messages,
                max_tokens=request.max_tokens or 1024,
                temperature=request.temperature,
            )

        try:
            message, _outcome = await retry_with_backoff(
                _do_request, max_attempts=3, is_retryable=_is_retryable, is_rate_limit=_is_rate_limit
            )
        except RetryExhaustedError as exc:
            raise AIProviderError(f"anthropic generate failed: {exc.__cause__}") from exc
        except Exception as exc:  # noqa: BLE001 — non-retryable (e.g. auth/bad request) fails on the first attempt
            raise AIProviderError(f"anthropic generate failed: {exc}") from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        text = "".join(block.text for block in message.content if getattr(block, "type", None) == "text")

        return AIResponse(
            provider=self.name,
            model=request.model,
            text=text,
            usage=AIUsage(
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            ),
            latency_ms=latency_ms,
            raw=message.model_dump(),
        )
