import asyncio
import random
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class RetryExhaustedError(RuntimeError):
    """Every retry attempt failed — wraps the last real error so callers
    still see the underlying cause, not just 'gave up'."""


@dataclass
class RetryOutcome:
    """Part H5 — how many attempts a call actually took, so callers can
    aggregate retry_count/rate_limit_events for EvaluationSummary without
    each provider adapter reinventing its own counter."""

    attempts: int
    rate_limited: bool  # True if any attempt was specifically identified as a rate-limit response


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 20.0,
    is_retryable: Callable[[Exception], bool] = lambda exc: True,
    is_rate_limit: Callable[[Exception], bool] = lambda exc: False,
    jitter: bool = True,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[T, RetryOutcome]:
    """Exponential backoff with jitter, bounded by max_attempts. Only
    retries exceptions `is_retryable` accepts — a real auth/config error
    (e.g. HTTP 401/403) must fail immediately, not burn attempts and time
    on something retrying can never fix. Raises RetryExhaustedError
    (chaining the last real exception) when every attempt is exhausted —
    never silently returns a partial/empty result."""
    last_exc: Exception | None = None
    rate_limited = False

    for attempt in range(1, max_attempts + 1):
        try:
            result = await fn()
            return result, RetryOutcome(attempts=attempt, rate_limited=rate_limited)
        except Exception as exc:  # noqa: BLE001 — re-raised as RetryExhaustedError if not retryable/exhausted
            if is_rate_limit(exc):
                rate_limited = True
            if not is_retryable(exc) or attempt == max_attempts:
                last_exc = exc
                break
            last_exc = exc
            delay = min(max_delay_seconds, base_delay_seconds * (2 ** (attempt - 1)))
            if jitter:
                delay *= 0.5 + random.random()
            await sleep(delay)

    raise RetryExhaustedError(f"all {max_attempts} attempts failed") from last_exc
