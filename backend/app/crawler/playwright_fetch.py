"""Async wrapper around app.crawler.playwright_worker — same OS-level
subprocess-isolation contract as app.crawler.subprocess_fetch, just
pointed at the headless-browser worker instead of the plain-HTTP one.
Returns the exact same FetchedPage/PageFetchFailed shape so callers in
crawl.py don't need to know which fetch strategy actually ran.
"""
import asyncio
import json
import sys

from app.crawler.extract import PageFacts
from app.crawler.subprocess_fetch import FetchedPage, PageFetchFailed

# A real browser launch + navigation is heavier than a plain HTTP GET —
# generous relative to subprocess_fetch's DEFAULT_KILL_TIMEOUT_SECONDS
# (25s), but still a hard, killable ceiling per the same Round 3 rationale.
DEFAULT_KILL_TIMEOUT_SECONDS = 45.0


async def fetch_with_playwright(
    url: str,
    site_hostname: str | None,
    user_agent: str,
    request_timeout_seconds: float,
    max_response_bytes: int,
    *,
    kill_timeout: float = DEFAULT_KILL_TIMEOUT_SECONDS,
) -> FetchedPage:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.crawler.playwright_worker",
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
        await proc.wait()
        raise PageFetchFailed(f"playwright fetch of {url} exceeded {kill_timeout}s and was killed")

    if proc.returncode != 0:
        raise PageFetchFailed(
            f"playwright worker for {url} exited {proc.returncode}: {stderr.decode(errors='replace')[:500]}"
        )

    try:
        payload = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise PageFetchFailed(f"playwright worker for {url} produced unparseable output: {exc}") from exc

    if not payload.get("ok"):
        raise PageFetchFailed(f"playwright fetch of {url} failed: {payload.get('error', 'unknown error')}")

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
