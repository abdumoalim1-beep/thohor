"""Part R2-F1 (Round 2 remediation) — deterministic store locale
resolution. All pure unit tests: no DB, no network, no AI — detect_locale
is a plain function over synthetic PageFacts, exactly like it runs inside
run_crawl_agent."""

import json
import uuid

from app.crawler.extract import PageFacts
from app.crawler.locale_detection import (
    RESOLVED_CONFIDENCE_THRESHOLD,
    detect_locale,
    resolve_locale_with_ai_fallback,
)
from app.providers.ai.base import AIProviderError, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute

_ARABIC_BODY = "منتجات وأسعار وتوصيل سريع لجميع أنحاء المملكة. تسوق الآن واحصل على أفضل العروض والخصومات لهذا الموسم في متجرنا الإلكتروني الرائد."
_ENGLISH_BODY = (
    "Shop the latest products with fast delivery nationwide. Browse our catalog of "
    "premium items and enjoy free shipping on every order over fifty dollars today."
)


def _product_json_ld(currency: str) -> dict:
    return {"@type": "Product", "name": "Widget", "offers": {"price": "10", "priceCurrency": currency}}


def _page(url, *, html_lang=None, hreflang=None, json_ld=None, body_text="", canonical=None) -> PageFacts:
    return PageFacts(
        url=url,
        title="t",
        html_lang=html_lang,
        hreflang=hreflang or {},
        json_ld=json_ld or [],
        body_text=body_text,
        canonical=canonical,
    )


def test_saudi_arabic_store_resolves_confidently():
    pages = [
        _page(
            "https://mystore.sa/",
            html_lang="ar",
            json_ld=[_product_json_ld("SAR")],
            body_text=_ARABIC_BODY * 5,
        )
        for _ in range(3)
    ]
    result = detect_locale(pages, "https://mystore.sa")
    assert result.status == "resolved"
    assert result.country == "sa"
    assert result.language == "ar"
    assert result.market == "SA"
    assert result.confidence >= RESOLVED_CONFIDENCE_THRESHOLD


def test_us_english_store_resolves_confidently_despite_generic_tld():
    """The exact Round 2 failure case: a .com domain with no ccTLD signal
    at all must still resolve to the US via currency + html lang + script,
    not silently fall through to a Saudi/Arabic default."""
    pages = [
        _page(
            "https://glossier-like.com/",
            html_lang="en-US",
            json_ld=[_product_json_ld("USD")],
            body_text=_ENGLISH_BODY * 5,
        )
        for _ in range(3)
    ]
    result = detect_locale(pages, "https://glossier-like.com")
    assert result.status == "resolved"
    assert result.country == "us"
    assert result.language == "en"


def test_uk_english_store_resolves_via_cctld():
    pages = [_page("https://mystore.co.uk/", html_lang="en-GB", body_text=_ENGLISH_BODY * 5)]
    result = detect_locale(pages, "https://mystore.co.uk")
    assert result.status == "resolved"
    assert result.country == "gb"
    assert result.language == "en"


def test_ambiguous_dot_com_with_no_signals_is_unresolved():
    pages = [_page("https://genericstore.com/", body_text="Welcome to our store.")]
    result = detect_locale(pages, "https://genericstore.com")
    assert result.status == "unresolved"
    assert result.country is None
    assert result.language is None


def test_missing_signals_entirely_is_unresolved_with_zero_confidence():
    pages = [_page("https://x.com/", body_text="")]
    result = detect_locale(pages, "https://x.com")
    assert result.status == "unresolved"
    assert result.confidence == 0.0
    assert result.source == "insufficient_signals"


def test_multilingual_site_resolves_the_crawled_pages_own_locale_via_hreflang_self_reference():
    """A site that serves multiple markets must not confuse 'this page's
    locale' with 'every locale the site happens to offer' — the crawled
    page's own hreflang self-reference should win, not the full alternate
    set."""
    pages = [
        _page(
            "https://global-store.com/en/",
            hreflang={"en-us": "https://global-store.com/en/", "ar-sa": "https://global-store.com/ar/"},
            html_lang="en",
            json_ld=[_product_json_ld("USD")],
            body_text=_ENGLISH_BODY * 3,
        )
    ]
    result = detect_locale(pages, "https://global-store.com")
    assert result.status == "resolved"
    assert result.country == "us"
    assert result.language == "en"


def test_conflicting_signals_produce_unresolved_rather_than_a_guess():
    """ccTLD says Saudi/Arabic, currency says US, html lang says English —
    a genuinely torn vote must land as unresolved, never silently pick a
    side with unearned confidence."""
    pages = [
        _page(
            "https://mystore.sa/",
            html_lang="en",
            json_ld=[_product_json_ld("USD")],
            body_text=_ENGLISH_BODY,
        )
    ]
    result = detect_locale(pages, "https://mystore.sa")
    assert result.status == "unresolved"
    assert result.confidence < RESOLVED_CONFIDENCE_THRESHOLD


def test_address_signal_is_the_strongest_and_wins_over_a_conflicting_cctld():
    pages = [
        _page(
            "https://mystore.sa/en-us/",
            json_ld=[
                {"@type": "Organization", "name": "Acme", "address": {"addressCountry": "US"}},
                _product_json_ld("USD"),
            ],
            hreflang={"en-us": "https://mystore.sa/en-us/"},
            html_lang="en",
            body_text=_ENGLISH_BODY * 3,
        )
    ]
    result = detect_locale(pages, "https://mystore.sa")
    assert result.status == "resolved"
    assert result.country == "us"
    assert result.language == "en"
    assert "address" in result.source


class _FakeLocaleGuessProvider:
    name = "fake_locale"

    def __init__(self, country="us", language="en", confidence=0.9):
        self._country, self._language, self._confidence = country, language, confidence
        self.calls = 0

    async def generate(self, request: AIRequest) -> AIResponse:
        self.calls += 1
        text = json.dumps({"country": self._country, "language": self._language, "confidence": self._confidence})
        return AIResponse(provider=self.name, model=request.model, text=text, usage=AIUsage(input_tokens=5, output_tokens=5))


class _FailingProvider:
    name = "failing_locale"

    async def generate(self, request: AIRequest) -> AIResponse:
        raise AIProviderError("simulated outage")


def _unresolved_result():
    return detect_locale([_page("https://x.com/", body_text="")], "https://x.com")


async def test_ai_fallback_is_never_consulted_once_deterministic_signals_resolve(session):
    """No router call at all when the deterministic pass already resolved
    — proves AI is strictly last-resort, never a shortcut."""
    resolved = detect_locale(
        [_page("https://mystore.sa/", html_lang="ar", json_ld=[_product_json_ld("SAR")], body_text=_ARABIC_BODY * 5)],
        "https://mystore.sa",
    )
    provider = _FakeLocaleGuessProvider()
    router = ModelRouter(providers={"fake": provider}, routes={"locale_resolution": TaskRoute(primary=ModelChoice("fake", "fake-model"))})

    out = await resolve_locale_with_ai_fallback(
        resolved, session=session, router=router, store_id=uuid.uuid4(), research_run_id=uuid.uuid4(),
        agent_run_id=None, store_context="irrelevant",
    )
    assert out is resolved
    assert provider.calls == 0


async def test_ai_fallback_fires_when_deterministic_pass_is_unresolved(session):
    provider = _FakeLocaleGuessProvider(country="us", language="en", confidence=0.9)
    router = ModelRouter(providers={"fake": provider}, routes={"locale_resolution": TaskRoute(primary=ModelChoice("fake", "fake-model"))})

    out = await resolve_locale_with_ai_fallback(
        _unresolved_result(), session=session, router=router, store_id=uuid.uuid4(), research_run_id=uuid.uuid4(),
        agent_run_id=None, store_context="some page evidence",
    )
    assert provider.calls == 1
    assert out.status == "resolved"
    assert out.country == "us"
    assert out.language == "en"
    assert out.source == "ai_fallback"


async def test_ai_fallback_confidence_is_capped_below_deterministic_certainty(session):
    """Even if the model claims high confidence, an AI guess must never
    read as more trustworthy than deterministic multi-signal agreement —
    capped at 0.65, comfortably below what 2+ real signals would produce."""
    provider = _FakeLocaleGuessProvider(country="us", language="en", confidence=0.99)
    router = ModelRouter(providers={"fake": provider}, routes={"locale_resolution": TaskRoute(primary=ModelChoice("fake", "fake-model"))})

    out = await resolve_locale_with_ai_fallback(
        _unresolved_result(), session=session, router=router, store_id=uuid.uuid4(), research_run_id=uuid.uuid4(),
        agent_run_id=None, store_context="x",
    )
    assert out.confidence <= 0.65


async def test_ai_fallback_provider_failure_leaves_locale_unresolved_not_crashed(session):
    router = ModelRouter(
        providers={"failing": _FailingProvider()},
        routes={"locale_resolution": TaskRoute(primary=ModelChoice("failing", "fake-model"))},
    )
    original = _unresolved_result()

    out = await resolve_locale_with_ai_fallback(
        original, session=session, router=router, store_id=uuid.uuid4(), research_run_id=uuid.uuid4(),
        agent_run_id=None, store_context="x",
    )
    assert out.status == "unresolved"
    assert out.country is None


def test_confidence_never_exceeds_one():
    pages = [
        _page(
            "https://mystore.sa/",
            html_lang="ar",
            hreflang={"ar-sa": "https://mystore.sa/"},
            json_ld=[
                {"@type": "Organization", "address": {"addressCountry": "SA"}},
                _product_json_ld("SAR"),
            ],
            body_text=_ARABIC_BODY * 5,
        )
    ]
    result = detect_locale(pages, "https://mystore.sa")
    assert result.confidence <= 1.0
