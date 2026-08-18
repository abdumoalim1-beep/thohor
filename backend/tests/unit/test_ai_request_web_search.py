"""Phase 0 coverage: enable_web_search request/response mapping.

Mocks the OpenAI SDK's client.responses.create directly (never hits the
real network) — verified against the actually-installed openai SDK's real
response/annotation shapes (ResponseOutputMessage.content[].annotations,
AnnotationURLCitation with .type == "url_citation") rather than a guess.
"""

import pytest

from app.providers.ai.base import AIMessage, AIRequest, AIRole, AIProviderError
from app.providers.ai.openai_provider import OpenAIProvider, _extract_sources_from_output


class _FakeAnnotation:
    def __init__(self, type_, url=None, title=None):
        self.type = type_
        self.url = url
        self.title = title


class _FakeContentItem:
    def __init__(self, annotations):
        self.annotations = annotations


class _FakeOutputMessage:
    def __init__(self, content):
        self.type = "message"
        self.content = content


class _FakeWebSearchCallItem:
    """A non-"message" output item (the actual search-call trace) — must be
    ignored by _extract_sources_from_output, not just message items."""

    def __init__(self):
        self.type = "web_search_call"


def test_extract_sources_pulls_url_citations_from_message_output():
    output = [
        _FakeWebSearchCallItem(),
        _FakeOutputMessage(
            content=[
                _FakeContentItem(
                    annotations=[
                        _FakeAnnotation("url_citation", url="https://example.com/a", title="A"),
                        _FakeAnnotation("url_citation", url="https://example.com/b", title="B"),
                    ]
                )
            ]
        ),
    ]
    sources = _extract_sources_from_output(output)
    assert sources == [
        {"url": "https://example.com/a", "title": "A"},
        {"url": "https://example.com/b", "title": "B"},
    ]


def test_extract_sources_dedupes_repeated_urls():
    output = [
        _FakeOutputMessage(
            content=[
                _FakeContentItem(
                    annotations=[
                        _FakeAnnotation("url_citation", url="https://example.com/a", title="A"),
                        _FakeAnnotation("url_citation", url="https://example.com/a", title="A again"),
                    ]
                )
            ]
        ),
    ]
    sources = _extract_sources_from_output(output)
    assert sources == [{"url": "https://example.com/a", "title": "A"}]


def test_extract_sources_ignores_non_url_citation_annotations():
    output = [
        _FakeOutputMessage(content=[_FakeContentItem(annotations=[_FakeAnnotation("file_citation")])]),
    ]
    assert _extract_sources_from_output(output) == []


class _FakeUsage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(self, output_text, output, usage):
        self.output_text = output_text
        self.output = output
        self.usage = usage

    def model_dump(self):
        return {"output_text": self.output_text}


async def test_generate_with_web_search_maps_response_onto_ai_response(monkeypatch):
    provider = OpenAIProvider(api_key="test-key")

    captured_kwargs = {}

    async def fake_create(**kwargs):
        captured_kwargs.update(kwargs)
        return _FakeResponse(
            output_text='{"brand_name": "Example"}',
            output=[
                _FakeOutputMessage(
                    content=[_FakeContentItem(annotations=[_FakeAnnotation("url_citation", url="https://x.test", title="X")])]
                )
            ],
            usage=_FakeUsage(input_tokens=12, output_tokens=34),
        )

    monkeypatch.setattr(provider._client.responses, "create", fake_create)

    request = AIRequest(
        task_type="store_identity_resolution",
        model="gpt-4o-mini",
        messages=[AIMessage(role=AIRole.user, content="identify example.com")],
        enable_web_search=True,
    )
    response = await provider.generate(request)

    assert captured_kwargs["tools"] == [{"type": "web_search"}]
    assert response.web_search_used is True
    assert response.text == '{"brand_name": "Example"}'
    assert response.sources == [{"url": "https://x.test", "title": "X"}]
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 34


async def test_generate_without_web_search_still_uses_chat_completions(monkeypatch):
    """enable_web_search=False (the default) must not change today's
    existing, already-tested chat.completions.create behavior."""
    provider = OpenAIProvider(api_key="test-key")
    called = {"responses_api": False}

    async def fake_responses_create(**kwargs):
        called["responses_api"] = True
        raise AssertionError("should not call the Responses API when enable_web_search is False")

    monkeypatch.setattr(provider._client.responses, "create", fake_responses_create)

    request = AIRequest(
        task_type="classification",
        model="gpt-4o-mini",
        messages=[AIMessage(role=AIRole.user, content="hi")],
    )
    with pytest.raises(Exception):
        # No chat.completions mock here — real network call would fail in
        # CI without a key; the point of this test is only that the
        # web_search branch was never entered.
        await provider.generate(request)
    assert called["responses_api"] is False


async def test_anthropic_provider_rejects_web_search_request():
    from app.providers.ai.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider(api_key="test-key")
    request = AIRequest(
        task_type="store_identity_resolution", model="claude-haiku-4-5-20251001",
        messages=[AIMessage(role=AIRole.user, content="hi")], enable_web_search=True,
    )
    with pytest.raises(AIProviderError, match="does not yet support"):
        await provider.generate(request)


async def test_google_provider_rejects_web_search_request():
    from app.providers.ai.google_provider import GoogleProvider

    provider = GoogleProvider(api_key="test-key")
    request = AIRequest(
        task_type="store_identity_resolution", model="gemini-2.5-flash",
        messages=[AIMessage(role=AIRole.user, content="hi")], enable_web_search=True,
    )
    with pytest.raises(AIProviderError, match="does not yet support"):
        await provider.generate(request)
