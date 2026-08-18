import asyncio

import httpx

from app.crawler.security import CrawlSecurityPolicy, UnsafeURLError, validate_url

ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/xml", "application/xml", "application/json")
MAX_REDIRECTS = 5


class FetchError(RuntimeError):
    pass


class FetchResult:
    def __init__(self, url: str, status_code: int, content_type: str, text: str):
        self.url = url
        self.status_code = status_code
        self.content_type = content_type
        self.text = text


async def _validate_url_async(url: str) -> None:
    """validate_url() calls socket.getaddrinfo(), a blocking syscall — run it
    off the event loop thread so one slow DNS lookup doesn't stall every
    other coroutine (every concurrent store's crawl, every other page fetch)
    sharing this process's single event loop. Same checks, same exceptions,
    non-blocking dispatch only."""
    await asyncio.get_running_loop().run_in_executor(None, validate_url, url)


async def safe_fetch(url: str, policy: CrawlSecurityPolicy) -> FetchResult:
    """Fetch a URL under the crawler security policy. Redirects are followed
    manually (not via httpx's follow_redirects) so every hop is re-validated
    against validate_url() — an open redirect must not become an SSRF path.
    """
    try:
        return await asyncio.wait_for(_safe_fetch_impl(url, policy), timeout=policy.request_timeout_seconds * 3)
    except asyncio.TimeoutError as exc:
        raise FetchError(f"request to {url} exceeded the overall wall-clock timeout") from exc
    except UnsafeURLError as exc:
        # validate_url() raising (DNS failure, private IP, disallowed scheme,
        # ...) is exactly as normal a single-URL failure as a network error —
        # it was previously left uncaught here, so it escaped safe_fetch()
        # entirely and crashed whatever loop called it instead of just
        # skipping that one URL (confirmed during Round 3 hardening: a
        # transient DNS failure on one page took down an entire crawl run).
        raise FetchError(f"request to {url} failed validation: {exc}") from exc


async def _safe_fetch_impl(url: str, policy: CrawlSecurityPolicy) -> FetchResult:
    """httpx's per-call timeout bounds each individual connect/read/write
    operation, not the total wall-clock time of a multi-redirect fetch — a
    server that trickles bytes slowly enough to keep individual reads under
    the timeout (confirmed during Round 3 live validation: a real page kept
    a crawl stalled far past its nominal request_timeout_seconds) can still
    hold a connection open indefinitely. safe_fetch() wraps this whole
    function in a hard wall-clock cap for exactly that reason."""
    await _validate_url_async(url)

    headers = {"User-Agent": policy.user_agent}
    current_url = url

    async with httpx.AsyncClient(follow_redirects=False, timeout=policy.request_timeout_seconds) as client:
        for _ in range(MAX_REDIRECTS):
            try:
                response = await client.get(current_url, headers=headers)
            except httpx.HTTPError as exc:
                raise FetchError(f"request to {current_url} failed: {exc}") from exc

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise FetchError(f"redirect from {current_url} had no Location header")
                next_url = str(httpx.URL(current_url).join(location))
                await _validate_url_async(next_url)
                current_url = next_url
                continue
            break
        else:
            raise FetchError(f"too many redirects starting from {url}")

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type and not any(content_type.startswith(ct) for ct in ALLOWED_CONTENT_TYPES):
        raise FetchError(f"disallowed content-type '{content_type}' for {current_url}")

    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > policy.max_response_bytes:
        raise FetchError(f"response too large ({content_length} bytes) for {current_url}")

    body = response.content
    if len(body) > policy.max_response_bytes:
        raise FetchError(f"response body exceeded max size for {current_url}")

    return FetchResult(
        url=current_url,
        status_code=response.status_code,
        content_type=content_type,
        text=body.decode(response.encoding or "utf-8", errors="replace"),
    )
