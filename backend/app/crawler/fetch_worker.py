"""Standalone subprocess entry point for one full page fetch: URL safety
validation, HTTP fetch (with redirects), and deterministic extraction, all
for exactly one URL.

Part of Round 3 crawler reliability hardening. Two separate, real hangs
were proven with timestamped evidence from live crawls of real stores:
  1. BeautifulSoup/lxml parsing a real IKEA Saudi page ran long enough
     that it never returned -- and because it's a CPU-bound C-extension
     call holding CPython's GIL, even `asyncio.wait_for(..., timeout=15)`
     wrapping it in-process never got a chance to fire: the event loop
     itself was starved, not just the one task.
  2. `validate_url()`'s DNS resolution (`socket.getaddrinfo`) on a
     transient failure took nearly 20 minutes to finally raise, ignoring
     every configured timeout on the path that was supposed to bound it.
No in-process timeout mechanism -- asyncio cancellation, threading,
signals -- can reliably bound either case, because all of them depend on
the same interpreter getting scheduled to run, or on the blocked call
cooperating with cancellation. A dedicated child process is the only
thing that can be terminated unconditionally regardless of what it's
doing internally, which is exactly why this whole operation (not just the
parse) runs here, in a process the caller can kill outright.

Invoked as:
  python -m app.crawler.fetch_worker <url> <site_hostname> <user_agent> <timeout_seconds> <max_response_bytes>
(site_hostname may be an empty string). Writes exactly one JSON object to
stdout:
  {"ok": true, "url": <final_url after redirects>, "status_code": ...,
   "content_type": ..., "html": ..., "title": ..., "h1": ..., ...}
  {"ok": false, "error": "..."}
Never raises past main() — every failure, expected or not, becomes a
structured {"ok": false} so the parent never has to guess whether a
non-zero exit was a crash or a normal single-page failure.
"""
import json
import sys

import httpx

from app.crawler.extract import extract_page_facts
from app.crawler.security import validate_url

ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/xml", "application/xml")
MAX_REDIRECTS = 5


class NonSuccessStatus(RuntimeError):
    """Raised specifically for a non-2xx final response, carrying the
    status code so the caller (crawl.py) can decide whether this looks
    like a bot-block worth retrying via the Playwright fallback, without
    needing to parse it back out of a generic error string."""

    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        super().__init__(f"non-success status {status_code} for {url}")


def _fetch_and_extract(url: str, site_hostname: str | None, user_agent: str, timeout_seconds: float, max_response_bytes: int):
    validate_url(url)

    headers = {"User-Agent": user_agent}
    current_url = url

    with httpx.Client(follow_redirects=False, timeout=timeout_seconds) as client:
        for _ in range(MAX_REDIRECTS):
            response = client.get(current_url, headers=headers)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise RuntimeError(f"redirect from {current_url} had no Location header")
                next_url = str(httpx.URL(current_url).join(location))
                validate_url(next_url)
                current_url = next_url
                continue
            break
        else:
            raise RuntimeError(f"too many redirects starting from {url}")

    if not (200 <= response.status_code < 300):
        # A non-2xx final response (most commonly a bot-detection/WAF
        # challenge page returning 403/429) must never be treated as a
        # successful fetch — it has no real page content, and silently
        # extracting facts from a challenge page produces a confident-
        # looking but garbage result instead of an honest failure.
        raise NonSuccessStatus(response.status_code, current_url)

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type and not any(content_type.startswith(ct) for ct in ALLOWED_CONTENT_TYPES):
        raise RuntimeError(f"disallowed content-type '{content_type}' for {current_url}")

    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > max_response_bytes:
        raise RuntimeError(f"response too large ({content_length} bytes) for {current_url}")

    body = response.content
    if len(body) > max_response_bytes:
        raise RuntimeError(f"response body exceeded max size for {current_url}")

    html = body.decode(response.encoding or "utf-8", errors="replace")
    facts = extract_page_facts(current_url, html, site_hostname)
    return current_url, response.status_code, content_type, html, facts


def main() -> int:
    url = sys.argv[1]
    site_hostname = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
    user_agent = sys.argv[3]
    timeout_seconds = float(sys.argv[4])
    max_response_bytes = int(sys.argv[5])

    try:
        final_url, status_code, content_type, html, facts = _fetch_and_extract(
            url, site_hostname, user_agent, timeout_seconds, max_response_bytes
        )
    except NonSuccessStatus as exc:
        # Status code surfaced explicitly (not buried in the error string)
        # so the caller can decide whether this looks like a bot-block
        # worth retrying via the Playwright fallback.
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc), "status_code": exc.status_code}))
        return 0
    except Exception as exc:  # noqa: BLE001 — any failure here is a normal single-page failure, never a crash
        sys.stdout.write(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 0

    payload = {
        "ok": True,
        "url": final_url,
        "status_code": status_code,
        "content_type": content_type,
        "html": html,
        "title": facts.title,
        "h1": facts.h1,
        "meta_description": facts.meta_description,
        "canonical": facts.canonical,
        "hreflang": facts.hreflang,
        "json_ld": facts.json_ld,
        "internal_links": facts.internal_links,
        "html_hash": facts.html_hash,
        "content_hash": facts.content_hash,
        "html_lang": facts.html_lang,
        "body_text": facts.body_text,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
