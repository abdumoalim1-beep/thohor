"""Async wrapper around app.crawler.fetch_worker — runs one full page
fetch (validate + HTTP GET with redirects + deterministic extraction) as
a genuine child process, so it can be killed at the OS level if it
exceeds its deadline. See fetch_worker.py's module docstring for the
evidence behind why this is necessary: neither the HTTP fetch nor the
HTML parse can be reliably bounded by an in-process timeout alone.
"""
import asyncio
import json
import sys
from dataclasses import dataclass, field

from app.crawler.extract import PageFacts

DEFAULT_KILL_TIMEOUT_SECONDS = 25.0


class PageFetchFailed(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, html: str | None = None):
        self.status_code = status_code
        # Only ever populated by the Playwright fallback path today (the
        # plain httpx worker doesn't return a body on failure) — lets
        # looks_like_bot_block() inspect the actual page content, not just
        # the status code, for the "200 but really a JS challenge" case.
        self.html = html
        super().__init__(message)


@dataclass
class FetchedPage:
    url: str
    status_code: int
    content_type: str
    html: str
    facts: PageFacts = field(repr=False)


async def fetch_and_extract_in_subprocess(
    url: str,
    site_hostname: str | None,
    user_agent: str,
    request_timeout_seconds: float,
    max_response_bytes: int,
    *,
    kill_timeout: float = DEFAULT_KILL_TIMEOUT_SECONDS,
) -> FetchedPage:
    """Spawns the worker, waits up to `kill_timeout` for it to finish, and
    kills it outright (SIGKILL / TerminateProcess) on timeout rather than
    waiting any longer — the actual guarantee this module exists for.
    Raises PageFetchFailed on any problem (timeout, non-zero exit,
    unparseable output, or a structured {"ok": false} from the worker
    itself) so the caller can treat every failure mode identically: skip
    this one page, keep crawling."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.crawler.fetch_worker",
        url,
        site_hostname or "",
        user_agent,
        str(request_timeout_seconds),
        str(max_response_bytes),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=kill_timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()  # reap the process so it doesn't linger as a zombie
        raise PageFetchFailed(f"fetch of {url} exceeded {kill_timeout}s and was killed")

    if proc.returncode != 0:
        raise PageFetchFailed(f"fetch worker for {url} exited {proc.returncode}: {stderr.decode(errors='replace')[:500]}")

    try:
        payload = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise PageFetchFailed(f"fetch worker for {url} produced unparseable output: {exc}") from exc

    if not payload.get("ok"):
        raise PageFetchFailed(
            f"fetch of {url} failed: {payload.get('error', 'unknown error')}",
            status_code=payload.get("status_code"),
        )

    facts = PageFacts(
        url=payload["url"],
        title=payload.get("title"),
        h1=payload.get("h1"),
        meta_description=payload.get("meta_description"),
        canonical=payload.get("canonical"),
        hreflang=payload.get("hreflang") or {},
        json_ld=payload.get("json_ld") or [],
        internal_links=payload.get("internal_links") or [],
        html_hash=payload.get("html_hash", ""),
        content_hash=payload.get("content_hash", ""),
        html_lang=payload.get("html_lang"),
        body_text=payload.get("body_text", ""),
    )
    return FetchedPage(
        url=payload["url"],
        status_code=payload["status_code"],
        content_type=payload.get("content_type", ""),
        html=payload.get("html", ""),
        facts=facts,
    )
