import pytest

from app.core.retry import RetryExhaustedError, retry_with_backoff


async def _no_sleep(_seconds: float) -> None:
    return None


async def test_retry_returns_result_on_first_success():
    async def fn():
        return "ok"

    result, outcome = await retry_with_backoff(fn, sleep=_no_sleep)
    assert result == "ok"
    assert outcome.attempts == 1


async def test_retry_succeeds_after_transient_failures():
    calls = {"count": 0}

    async def fn():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result, outcome = await retry_with_backoff(fn, max_attempts=5, sleep=_no_sleep)
    assert result == "ok"
    assert outcome.attempts == 3
    assert calls["count"] == 3


async def test_retry_exhausts_and_raises_with_original_cause():
    async def fn():
        raise RuntimeError("always fails")

    with pytest.raises(RetryExhaustedError) as exc_info:
        await retry_with_backoff(fn, max_attempts=3, sleep=_no_sleep)

    assert isinstance(exc_info.value.__cause__, RuntimeError)


async def test_retry_does_not_retry_non_retryable_errors():
    calls = {"count": 0}

    async def fn():
        calls["count"] += 1
        raise ValueError("auth error, retrying won't help")

    with pytest.raises(RetryExhaustedError):
        await retry_with_backoff(
            fn, max_attempts=5, sleep=_no_sleep, is_retryable=lambda exc: not isinstance(exc, ValueError)
        )

    assert calls["count"] == 1  # stopped immediately, no wasted retries


async def test_retry_tracks_rate_limit_flag():
    calls = {"count": 0}

    async def fn():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("429")
        return "ok"

    result, outcome = await retry_with_backoff(
        fn, max_attempts=3, sleep=_no_sleep, is_rate_limit=lambda exc: "429" in str(exc)
    )
    assert result == "ok"
    assert outcome.rate_limited is True
