"""Standalone subprocess entry point for one full page fetch via a real
headless browser — the fallback path for pages that respond with a bot-
detection/challenge page (403, or a 200 that's actually a JS-rendered
interstitial) to the plain httpx-based fetch in fetch_worker.py.

Deliberately mirrors fetch_worker.py's contract exactly (same stdout JSON
shape, same subprocess-isolation rationale — a hung browser process is at
least as plausible a failure mode as a hung DNS lookup or a slow lxml
parse, so this needs the same OS-level-killable guarantee, not a lighter
one) so it slots into the same fetch_candidate() call site in crawl.py
with only a different subprocess module name.

Invoked as:
  python -m app.crawler.playwright_worker <url> <site_hostname> <user_agent> <timeout_seconds> <max_response_bytes>
Writes exactly one JSON object to stdout, same shape as fetch_worker.py:
  {"ok": true, "url": <final_url>, "status_code": ..., "content_type": ..., "html": ..., ...}
  {"ok": false, "error": "..."}
"""
import json
import sys

from app.crawler.extract import extract_page_facts
from app.crawler.security import validate_url

MAX_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


def _fetch_and_extract(url: str, site_hostname: str | None, user_agent: str, timeout_seconds: float, max_response_bytes: int):
    validate_url(url)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(user_agent=user_agent)
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            if response is None:
                raise RuntimeError(f"no response received for {url}")

            final_url = page.url
            # Post-navigation SSRF check: the browser follows redirects
            # internally, so unlike fetch_worker.py's per-hop httpx check,
            # this only catches a malicious final destination after the
            # fact — reasonable defense-in-depth for a fallback path that's
            # only ever invoked against the store's own (or, later, a
            # confirmed competitor's) domain, not arbitrary user input.
            validate_url(final_url)

            status_code = response.status
            if not (200 <= status_code < 300):
                raise RuntimeError(f"non-success status {status_code} for {final_url}")

            content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            if content_type and not any(content_type.startswith(ct) for ct in MAX_CONTENT_TYPES):
                raise RuntimeError(f"disallowed content-type '{content_type}' for {final_url}")

            html = page.content()
            if len(html.encode("utf-8")) > max_response_bytes:
                raise RuntimeError(f"response body exceeded max size for {final_url}")
        finally:
            browser.close()

    facts = extract_page_facts(final_url, html, site_hostname)
    return final_url, status_code, content_type, html, facts


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
