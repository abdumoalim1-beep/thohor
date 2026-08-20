import time

import openai
from openai import AsyncOpenAI

from app.core.retry import RetryExhaustedError, retry_with_backoff
from app.providers.ai.base import AIProvider, AIProviderError, AIRequest, AIResponse, AIUsage

# Part H5 — the SDK's own default retrying (max_retries=2) is disabled below
# (max_retries=0) so every retry goes through our uniform retry_with_backoff
# instead: one retry_count/rate_limit_events accounting path across all
# providers (SerpAPI, OpenAI, Anthropic, Google), not a mix of SDK-internal
# and app-level retries with unrelated backoff schedules.
_RETRYABLE_EXCEPTIONS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, _RETRYABLE_EXCEPTIONS)


def _is_rate_limit(exc: Exception) -> bool:
    return isinstance(exc, openai.RateLimitError)


def _web_search_was_invoked(output: list) -> bool:
    """tool_choice="required" forces the model to call *a* tool, and
    web_search is the only one offered — but this checks the actual
    response for a web_search_call item rather than assuming the forcing
    worked, so web_search_used never claims a search happened that
    didn't."""
    return any(getattr(item, "type", None) == "web_search_call" for item in output)


def _extract_sources_from_output(output: list) -> list[dict]:
    """Pulls url_citation annotations out of a Responses API output array.
    Verified against the actually-installed openai SDK's real types
    (ResponseOutputMessage.content[].annotations, AnnotationURLCitation) —
    not guessed from documentation."""
    sources: list[dict] = []
    seen_urls: set[str] = set()
    for item in output:
        if getattr(item, "type", None) != "message":
            continue
        for content_item in getattr(item, "content", []) or []:
            for annotation in getattr(content_item, "annotations", []) or []:
                if getattr(annotation, "type", None) != "url_citation":
                    continue
                url = annotation.url
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                sources.append({"url": url, "title": annotation.title})
    return sources


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str):
        self._client = AsyncOpenAI(api_key=api_key, max_retries=0)

    async def generate(self, request: AIRequest) -> AIResponse:
        if request.enable_web_search:
            return await self._generate_with_web_search(request)

        start = time.monotonic()

        async def _do_request():
            return await self._client.chat.completions.create(
                model=request.model,
                messages=[{"role": m.role.value, "content": m.content} for m in request.messages],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )

        try:
            completion, _outcome = await retry_with_backoff(
                _do_request, max_attempts=3, is_retryable=_is_retryable, is_rate_limit=_is_rate_limit
            )
        except RetryExhaustedError as exc:
            raise AIProviderError(f"openai generate failed: {exc.__cause__}") from exc
        except Exception as exc:  # noqa: BLE001 — non-retryable (e.g. auth/bad request) fails on the first attempt
            raise AIProviderError(f"openai generate failed: {exc}") from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        choice = completion.choices[0].message.content or ""
        usage = completion.usage

        return AIResponse(
            provider=self.name,
            model=request.model,
            text=choice,
            usage=AIUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
            latency_ms=latency_ms,
            raw=completion.model_dump(),
        )

    async def _generate_with_web_search(self, request: AIRequest) -> AIResponse:
        """Uses the Responses API (not Chat Completions) — the only OpenAI
        API surface that offers the hosted web_search tool. Response shape
        verified against the installed SDK, not assumed.

        tool_choice="required" is load-bearing, not decoration: with the
        default "auto", the model is free to skip the tool entirely and
        answer from its own training data instead — verified live against
        this exact prompt shape, where it did exactly that (zero
        web_search_call items, zero citations) for a short buyer-intent
        question. That silently turns "does AI search find this store"
        into "is this store famous enough to be in training data", which
        is a different and much weaker signal than every caller of
        enable_web_search actually wants."""
        start = time.monotonic()

        async def _do_request():
            return await self._client.responses.create(
                model=request.model,
                input=[{"role": m.role.value, "content": m.content} for m in request.messages],
                tools=[{"type": "web_search"}],
                tool_choice="required",
                temperature=request.temperature,
                max_output_tokens=request.max_tokens,
            )

        try:
            response, _outcome = await retry_with_backoff(
                _do_request, max_attempts=3, is_retryable=_is_retryable, is_rate_limit=_is_rate_limit
            )
        except RetryExhaustedError as exc:
            raise AIProviderError(f"openai web_search generate failed: {exc.__cause__}") from exc
        except Exception as exc:  # noqa: BLE001 — non-retryable fails on the first attempt
            raise AIProviderError(f"openai web_search generate failed: {exc}") from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        text = response.output_text or ""
        sources = _extract_sources_from_output(response.output)
        usage = response.usage

        return AIResponse(
            provider=self.name,
            model=request.model,
            text=text,
            usage=AIUsage(
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
            ),
            latency_ms=latency_ms,
            raw=response.model_dump(),
            web_search_used=_web_search_was_invoked(response.output),
            sources=sources,
        )
