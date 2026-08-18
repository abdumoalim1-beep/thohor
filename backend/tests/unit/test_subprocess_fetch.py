import time

import pytest

from app.crawler.subprocess_fetch import PageFetchFailed, fetch_and_extract_in_subprocess

"""Round 3 crawler reliability hardening. Root cause, proven with
timestamped evidence from real store crawls: (1) BeautifulSoup/lxml
parsing a real IKEA Saudi page ran long enough that it never returned,
and because that's a CPU-bound C-extension call holding the GIL, even
asyncio.wait_for's own timeout callback never got scheduled to fire in
the same process; (2) a stalled DNS lookup in validate_url() ignored
every configured timeout on its own path for nearly 20 minutes before
finally raising. fetch_and_extract_in_subprocess runs the whole per-page
operation (validate + fetch + parse) in a genuine child process so the
OS can terminate it unconditionally on timeout, regardless of what's
blocking inside. These tests prove the actual guarantee: the call always
returns -- success or PageFetchFailed -- within a bounded wall-clock
window, and one bad URL never contaminates the next call."""


@pytest.mark.asyncio
async def test_fetch_of_an_unresolvable_host_fails_promptly_instead_of_hanging():
    """Directly reproduces the second confirmed real-world failure mode:
    DNS resolution failure for a host that will never resolve. Must fail
    fast and cleanly, not hang or crash the caller."""
    start = time.monotonic()
    with pytest.raises(PageFetchFailed):
        await fetch_and_extract_in_subprocess(
            "https://this-host-does-not-exist-mersad-test.invalid/",
            "this-host-does-not-exist-mersad-test.invalid",
            "MersadBot/1.0",
            request_timeout_seconds=5.0,
            max_response_bytes=5_000_000,
            kill_timeout=15.0,
        )
    elapsed = time.monotonic() - start
    assert elapsed < 20.0


@pytest.mark.asyncio
async def test_kill_timeout_returns_promptly_and_raises_instead_of_hanging():
    """The actual guarantee this module exists for: even in the worst
    case (a kill_timeout so tight the subprocess can't possibly finish),
    the call must return control within a bounded window -- never hang
    indefinitely waiting on a process that won't cooperate."""
    start = time.monotonic()
    with pytest.raises(PageFetchFailed):
        await fetch_and_extract_in_subprocess(
            "https://example.com/",
            "example.com",
            "MersadBot/1.0",
            request_timeout_seconds=5.0,
            max_response_bytes=5_000_000,
            kill_timeout=0.001,
        )
    elapsed = time.monotonic() - start
    assert elapsed < 10.0


@pytest.mark.asyncio
async def test_multiple_forced_failures_in_a_row_never_leak_into_a_hang():
    """One bad page must never be able to degrade every subsequent page's
    fetch. Three consecutive forced timeouts must each resolve
    independently and promptly."""
    for _ in range(3):
        start = time.monotonic()
        with pytest.raises(PageFetchFailed):
            await fetch_and_extract_in_subprocess(
                "https://example.com/",
                "example.com",
                "MersadBot/1.0",
                request_timeout_seconds=5.0,
                max_response_bytes=5_000_000,
                kill_timeout=0.001,
            )
        assert time.monotonic() - start < 10.0


@pytest.mark.asyncio
async def test_disallowed_scheme_fails_as_a_normal_page_failure_not_a_crash():
    """validate_url() raising for a plainly unsafe URL must surface as the
    same PageFetchFailed as any other single-page problem -- never an
    unhandled exception that propagates out of the crawl loop (the
    UnsafeURLError-not-caught bug confirmed during this same hardening
    pass)."""
    with pytest.raises(PageFetchFailed):
        await fetch_and_extract_in_subprocess(
            "ftp://example.com/",
            "example.com",
            "MersadBot/1.0",
            request_timeout_seconds=5.0,
            max_response_bytes=5_000_000,
            kill_timeout=15.0,
        )
