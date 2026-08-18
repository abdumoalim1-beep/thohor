import httpx
import pytest

from app.crawler import fetch_worker


class _FakeResponse:
    def __init__(self, status_code: int, body: bytes = b"<html><body>ok</body></html>"):
        self.status_code = status_code
        self.headers: dict[str, str] = {"content-type": "text/html"}
        self.content = body
        self.encoding = "utf-8"


def test_non_success_status_is_treated_as_a_failure_not_a_successful_fetch(monkeypatch):
    """The real-world case this closes: a bot-detection/WAF challenge page
    responds 403 with an HTML body — previously that body was silently
    extracted and treated as real page content."""

    def fake_get(self, url, headers=None):
        return _FakeResponse(403)

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    with pytest.raises(RuntimeError, match="non-success status 403"):
        fetch_worker._fetch_and_extract("https://example.com", "example.com", "TestBot/1.0", 5.0, 1_000_000)


def test_rate_limited_status_is_also_treated_as_a_failure(monkeypatch):
    def fake_get(self, url, headers=None):
        return _FakeResponse(429)

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    with pytest.raises(RuntimeError, match="non-success status 429"):
        fetch_worker._fetch_and_extract("https://example.com", "example.com", "TestBot/1.0", 5.0, 1_000_000)


def test_a_genuine_200_response_still_succeeds(monkeypatch):
    """The fix must not reject legitimate successful fetches."""

    def fake_get(self, url, headers=None):
        return _FakeResponse(200, b"<html><head><title>Real Page</title></head><body>content</body></html>")

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    final_url, status_code, content_type, html, facts = fetch_worker._fetch_and_extract(
        "https://example.com", "example.com", "TestBot/1.0", 5.0, 1_000_000
    )
    assert status_code == 200
    assert facts.title == "Real Page"
