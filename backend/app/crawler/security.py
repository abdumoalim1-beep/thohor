"""SSRF and abuse guards for the crawler. Every URL — including each
redirect hop — must pass validate_url() before a request is issued. This is
mandatory groundwork per the plan, not optional hardening: the crawler
fetches arbitrary, user-supplied store URLs.
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}

# Cloud metadata endpoints that must never be reachable via a crawled URL.
BLOCKED_HOSTS = {
    "169.254.169.254",  # AWS/GCP/Azure instance metadata
    "metadata.google.internal",
}


class UnsafeURLError(ValueError):
    pass


@dataclass(frozen=True)
class CrawlSecurityPolicy:
    max_response_bytes: int
    request_timeout_seconds: float
    user_agent: str


def _is_private_or_reserved(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # Not a parseable IP literal — getaddrinfo already validated it's a
        # routable address for its family, so treat as safe-to-continue
        # rather than blocking on something we can't evaluate.
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


# Deliberately narrow and high-confidence only — a false positive here
# (flagging a genuinely small/empty store as "blocked") is worse than a
# false negative (missing an unusual challenge provider), since it changes
# what the user is told about their own store. Keep this list conservative;
# widen only on confirmed real-world misses, not speculatively.
_BOT_BLOCK_HTML_MARKERS = (
    "checking your browser before accessing",  # Cloudflare "I'm Under Attack" interstitial
    "cf-browser-verification",
    "cf-chl-",
    "just a moment...",  # Cloudflare's newer challenge page title
    "attention required! | cloudflare",
    "distil_r_captcha",  # Akamai/Distil
    "perimeterx",
    "px-captcha",
    "access denied",
)
_BOT_BLOCK_STATUS_CODES = (403, 429, 503)


def looks_like_bot_block(html: str | None, status: int | None) -> bool:
    """Best-effort, conservative heuristic — never a certainty. Used only
    to distinguish "this crawl came back empty because the site actively
    blocked us" (Store.catalog_status = "blocked", still shown honestly to
    the user with a retry option) from "this crawl came back empty because
    the store genuinely has little content" (catalog_status = "ready",
    just a small site). A miss either way degrades gracefully — it only
    changes the wording shown, never fabricates data."""
    if status is not None and status in _BOT_BLOCK_STATUS_CODES:
        return True
    if not html:
        return False
    lowered = html.lower()
    return any(marker in lowered for marker in _BOT_BLOCK_HTML_MARKERS)


def validate_url(url: str) -> None:
    """Raises UnsafeURLError if the URL must not be fetched. Resolves the
    hostname and checks the *resolved* IP (not just the hostname string) to
    close DNS-rebinding style bypasses."""

    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme '{parsed.scheme}' is not allowed (http/https only)")

    if not parsed.hostname:
        raise UnsafeURLError("URL has no hostname")

    hostname = parsed.hostname.lower()
    if hostname in BLOCKED_HOSTS or hostname == "localhost":
        raise UnsafeURLError(f"host '{hostname}' is blocked")

    try:
        resolved_ips = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise UnsafeURLError(f"could not resolve host '{hostname}'") from exc

    for ip_str in resolved_ips:
        if ip_str in BLOCKED_HOSTS:
            raise UnsafeURLError(f"host '{hostname}' resolves to a blocked IP")
        if _is_private_or_reserved(ip_str):
            raise UnsafeURLError(f"host '{hostname}' resolves to a private/reserved IP ({ip_str})")
