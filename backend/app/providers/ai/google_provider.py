import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.retry import RetryExhaustedError, retry_with_backoff
from app.providers.ai.base import AIProvider, AIProviderError, AIRequest, AIResponse, AIRole, AIUsage

# Part H5 — google-genai raises ClientError for 4xx and ServerError for 5xx,
# both carrying a `.code` (HTTP status). Only 429 within ClientError is
# retryable — other 4xx (bad request, auth) are not transient.
_RETRYABLE_SERVER_ERROR = genai_errors.ServerError


def _is_rate_limit(exc: Exception) -> bool:
    return isinstance(exc, genai_errors.ClientError) and getattr(exc, "code", None) == 429


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, _RETRYABLE_SERVER_ERROR) or _is_rate_limit(exc)


class GoogleProvider(AIProvider):
    name = "google"

    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

    async def generate(self, request: AIRequest) -> AIResponse:
        if request.enable_web_search:
            # Gemini's google_search grounding tool isn't wired up yet
            # (planned for the multi-engine visibility phase, as a separate
            # "google_grounded" provider so the existing non-grounded
            # surface stays honestly labeled search_enabled=False) — fail
            # loudly rather than silently answering ungrounded.
            raise AIProviderError("google provider does not yet support enable_web_search")
        start = time.monotonic()
        system_prompt = "\n".join(m.content for m in request.messages if m.role == AIRole.system) or None
        contents = "\n".join(m.content for m in request.messages if m.role != AIRole.system)

        async def _do_request():
            return await self._client.aio.models.generate_content(
                model=request.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=request.max_tokens,
                    temperature=request.temperature,
                ),
            )

        try:
            response, _outcome = await retry_with_backoff(
                _do_request, max_attempts=3, is_retryable=_is_retryable, is_rate_limit=_is_rate_limit
            )
        except RetryExhaustedError as exc:
            raise AIProviderError(f"google generate failed: {exc.__cause__}") from exc
        except Exception as exc:  # noqa: BLE001 — non-retryable (e.g. auth/bad request) fails on the first attempt
            raise AIProviderError(f"google generate failed: {exc}") from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        usage = response.usage_metadata

        return AIResponse(
            provider=self.name,
            model=request.model,
            text=response.text or "",
            usage=AIUsage(
                input_tokens=usage.prompt_token_count if usage else 0,
                output_tokens=usage.candidates_token_count if usage else 0,
            ),
            latency_ms=latency_ms,
            raw={"text": response.text},
        )
