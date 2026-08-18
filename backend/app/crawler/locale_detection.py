"""Part R2-F1 (Round 2 remediation) — deterministic-first store locale
resolution.

Confirmed root cause: `Store.country`/`Store.language` were never
populated by anything, so `app.orchestrator.research_orchestrator` (and
`app.research.loop`) silently fell back to `Settings.serp_default_country`/
`serp_default_language` ("sa"/"ar") for EVERY store regardless of its real
market. Round 2's live audits confirmed this produced nonsense competitors
(a pharmacy-delivery app, a food-delivery app, a cybersecurity vendor) and
an Arabic-only measurement pass for real US brands (glossier.com,
chewy.com), and — checked retroactively — Round 1's allbirds.com too.

This module combines multiple independent, purely-deterministic signals
already available from the pages crawled this run (no new network calls,
no AI): each signal "votes" for a (country, language) candidate with a
fixed weight reflecting how trustworthy that signal is. AI is never the
primary source — see `resolve_locale_with_ai_fallback` below, only ever
invoked by the caller when this deterministic pass is inconclusive.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.core.domain import parse_domain
from app.crawler.extract import PageFacts

# --- signal weights (explicit precedence, highest first) -----------------
_WEIGHT_ADDRESS = 1.0
_WEIGHT_CCTLD = 0.9
_WEIGHT_CURRENCY = 0.75
_WEIGHT_URL_LOCALE_CODE = 0.6
_WEIGHT_HREFLANG_SELF = 0.55
_WEIGHT_HTML_LANG = 0.5
_WEIGHT_MARKET_PHRASE = 0.45
_WEIGHT_SCRIPT = 0.3

# A store is only ever marked "resolved" above this bar on BOTH axes
# (country and language) — below it, the honest answer is "we don't know",
# never an invented sa/ar default (see resolve_locale_with_ai_fallback and
# the orchestrator call site for what happens next).
RESOLVED_CONFIDENCE_THRESHOLD = 0.55

# Deliberately small, explicit, documented tables — not an attempt at
# exhaustive geo/currency coverage. Extending them is safe and additive;
# an unmapped ccTLD/currency simply doesn't vote, it never guesses.
_CCTLD_LOCALE: dict[str, tuple[str, str]] = {
    "sa": ("sa", "ar"), "ae": ("ae", "ar"), "eg": ("eg", "ar"), "kw": ("kw", "ar"),
    "qa": ("qa", "ar"), "bh": ("bh", "ar"), "om": ("om", "ar"), "jo": ("jo", "ar"),
    "iq": ("iq", "ar"), "ma": ("ma", "ar"),
    "co.uk": ("gb", "en"), "uk": ("gb", "en"),
    "us": ("us", "en"), "ca": ("ca", "en"), "au": ("au", "en"), "nz": ("nz", "en"),
    "de": ("de", "de"), "fr": ("fr", "fr"), "es": ("es", "es"), "it": ("it", "it"),
    "in": ("in", "en"),
}
# Generic/global TLDs never vote — a .com/.net/.store/.shop tells us nothing.
_GENERIC_TLDS = {"com", "net", "org", "io", "co", "shop", "store", "app", "online"}

_CURRENCY_COUNTRY: dict[str, str] = {
    "usd": "us", "sar": "sa", "gbp": "gb", "aed": "ae", "egp": "eg",
    "kwd": "kw", "qar": "qa", "cad": "ca", "aud": "au",
}
_COUNTRY_NAME_ALIASES: dict[str, str] = {
    "united states": "us", "united states of america": "us", "usa": "us", "us": "us",
    "saudi arabia": "sa", "kingdom of saudi arabia": "sa", "sa": "sa",
    "united kingdom": "gb", "great britain": "gb", "uk": "gb", "gb": "gb",
    "united arab emirates": "ae", "uae": "ae", "ae": "ae",
    "canada": "ca", "australia": "au", "egypt": "eg", "kuwait": "kw",
}
_URL_LOCALE_CODE_RE = re.compile(r"[/.](?:^|[-_])?(ar|en)[-_](sa|ae|us|gb|eg|kw|qa)\b|[/.](ar|en)(?=[/.]|$)", re.IGNORECASE)
_MARKET_PHRASES: list[tuple[re.Pattern, str, str | None]] = [
    (re.compile(r"ship(?:ping)? to (?:the )?united states|free shipping.{0,15}\bu\.?s\.?a?\b", re.IGNORECASE), "us", "en"),
    (re.compile(r"ship(?:ping)? to (?:the )?united kingdom|free uk delivery", re.IGNORECASE), "gb", "en"),
    (re.compile(r"الشحن\s+(?:إلى|الى|داخل)\s+(?:المملكة العربية السعودية|السعودية)"), "sa", "ar"),
    (re.compile(r"شحن\s+مجاني\s+داخل\s+المملكة"), "sa", "ar"),
]
_ARABIC_SCRIPT_RE = re.compile(r"[؀-ۿ]")
_LATIN_SCRIPT_RE = re.compile(r"[A-Za-z]")


@dataclass
class LocaleSignal:
    name: str
    weight: float
    country: str | None = None
    language: str | None = None
    detail: str = ""


@dataclass
class LocaleDetectionResult:
    country: str | None
    language: str | None
    market: str | None
    confidence: float
    source: str
    status: str  # "resolved" | "unresolved"
    signals: list[LocaleSignal] = field(default_factory=list)


def _signal_from_cctld(base_url: str) -> LocaleSignal | None:
    parts = parse_domain(base_url)
    suffix = parts.suffix.lower()
    if suffix in _GENERIC_TLDS or not suffix:
        return None
    match = _CCTLD_LOCALE.get(suffix)
    if match is None:
        # a two-part suffix like "com.sa" still carries a real ccTLD signal
        tld_tail = suffix.rsplit(".", 1)[-1]
        match = _CCTLD_LOCALE.get(tld_tail)
    if match is None:
        return None
    country, language = match
    return LocaleSignal("cctld", _WEIGHT_CCTLD, country=country, language=language, detail=suffix)


def _iter_json_ld(pages: list[PageFacts]):
    for page in pages:
        yield from page.json_ld


def _signal_from_address(pages: list[PageFacts]) -> LocaleSignal | None:
    for entry in _iter_json_ld(pages):
        address = entry.get("address")
        if isinstance(address, dict):
            raw = address.get("addressCountry")
        else:
            raw = None
        if not raw:
            continue
        code = _COUNTRY_NAME_ALIASES.get(str(raw).strip().lower())
        if code:
            return LocaleSignal("address", _WEIGHT_ADDRESS, country=code, detail=str(raw))
    return None


def _signal_from_currency(pages: list[PageFacts]) -> LocaleSignal | None:
    counts: dict[str, int] = defaultdict(int)
    for entry in _iter_json_ld(pages):
        raw_types = entry.get("@type")
        types = [raw_types] if isinstance(raw_types, str) else (raw_types or [])
        if "Product" not in types and "ProductGroup" not in types:
            continue
        offers = entry.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        currency = offers.get("priceCurrency")
        if currency:
            counts[str(currency).strip().lower()] += 1
    if not counts:
        return None
    top_currency = max(counts, key=lambda c: counts[c])
    country = _CURRENCY_COUNTRY.get(top_currency)
    if country is None:
        return None
    return LocaleSignal("currency", _WEIGHT_CURRENCY, country=country, detail=top_currency)


def _signal_from_url_locale_code(pages: list[PageFacts]) -> LocaleSignal | None:
    votes: dict[tuple[str | None, str | None], int] = defaultdict(int)
    for page in pages:
        m = _URL_LOCALE_CODE_RE.search(page.url)
        if not m:
            continue
        if m.group(1) and m.group(2):
            votes[(m.group(2).lower(), m.group(1).lower())] += 1
        elif m.group(3):
            votes[(None, m.group(3).lower())] += 1
    if not votes:
        return None
    (country, language), _ = max(votes.items(), key=lambda kv: kv[1])
    return LocaleSignal("url_locale_code", _WEIGHT_URL_LOCALE_CODE, country=country, language=language)


def _signal_from_hreflang(pages: list[PageFacts]) -> LocaleSignal | None:
    votes: dict[str, int] = defaultdict(int)
    for page in pages:
        for code, href in page.hreflang.items():
            if code.lower() == "x-default":
                continue
            if href.rstrip("/") == page.url.rstrip("/"):
                votes[code.lower()] += 1
                break
    if not votes:
        return None
    top_code, _ = max(votes.items(), key=lambda kv: kv[1])
    language = top_code.split("-")[0]
    country = top_code.split("-")[1] if "-" in top_code else None
    return LocaleSignal("hreflang_self", _WEIGHT_HREFLANG_SELF, country=country, language=language, detail=top_code)


def _signal_from_html_lang(pages: list[PageFacts]) -> LocaleSignal | None:
    votes: dict[str, int] = defaultdict(int)
    for page in pages:
        if page.html_lang:
            votes[page.html_lang.strip().lower()] += 1
    if not votes:
        return None
    top_code, _ = max(votes.items(), key=lambda kv: kv[1])
    language = top_code.split("-")[0]
    country = top_code.split("-")[1] if "-" in top_code else None
    return LocaleSignal("html_lang", _WEIGHT_HTML_LANG, country=country, language=language, detail=top_code)


def _signal_from_market_phrases(pages: list[PageFacts]) -> LocaleSignal | None:
    for page in pages:
        for pattern, country, language in _MARKET_PHRASES:
            if pattern.search(page.body_text):
                return LocaleSignal("market_phrase", _WEIGHT_MARKET_PHRASE, country=country, language=language)
    return None


def _signal_from_script_ratio(pages: list[PageFacts]) -> LocaleSignal | None:
    """The weakest signal by design — it can only distinguish broad script
    families (Arabic vs. Latin), never specific languages within a script
    (English vs. French) or countries. Only fires on a lopsided ratio; a
    genuinely mixed/bilingual site correctly produces no vote here."""
    arabic = latin = 0
    for page in pages:
        arabic += len(_ARABIC_SCRIPT_RE.findall(page.body_text))
        latin += len(_LATIN_SCRIPT_RE.findall(page.body_text))
    total = arabic + latin
    if total < 200:  # not enough text sampled to trust a ratio at all
        return None
    if arabic / total >= 0.6:
        return LocaleSignal("script_ratio", _WEIGHT_SCRIPT, language="ar", detail=f"{arabic}/{total} arabic")
    if latin / total >= 0.85:
        return LocaleSignal("script_ratio", _WEIGHT_SCRIPT, language="en", detail=f"{latin}/{total} latin")
    return None


def _pick_winner(votes: dict[str, float]) -> tuple[str | None, float]:
    if not votes:
        return None, 0.0
    ranked = sorted(votes.items(), key=lambda kv: kv[1], reverse=True)
    top_value, top_weight = ranked[0]
    second_weight = ranked[1][1] if len(ranked) > 1 else 0.0
    dominance = top_weight / (top_weight + second_weight) if (top_weight + second_weight) > 0 else 0.0
    strength = min(top_weight / _WEIGHT_ADDRESS, 1.0)
    return top_value, dominance * strength


def detect_locale(pages: list[PageFacts], base_url: str) -> LocaleDetectionResult:
    """Pure and deterministic — no network, no AI, safe to call in any
    evaluation mode including replay/tests. `pages` are the PageFacts
    already produced by this run's crawl; no re-fetch happens here."""
    signals = [
        s
        for s in (
            _signal_from_address(pages),
            _signal_from_cctld(base_url),
            _signal_from_currency(pages),
            _signal_from_url_locale_code(pages),
            _signal_from_hreflang(pages),
            _signal_from_html_lang(pages),
            _signal_from_market_phrases(pages),
            _signal_from_script_ratio(pages),
        )
        if s is not None
    ]

    country_votes: dict[str, float] = defaultdict(float)
    language_votes: dict[str, float] = defaultdict(float)
    contributors: dict[str, set[str]] = defaultdict(set)
    for s in signals:
        if s.country:
            country_votes[s.country] += s.weight
            contributors[s.country].add(s.name)
        if s.language:
            language_votes[s.language] += s.weight
            contributors[s.language].add(s.name)

    country, country_confidence = _pick_winner(country_votes)
    language, language_confidence = _pick_winner(language_votes)

    if country and language:
        confidence = (country_confidence + language_confidence) / 2
    elif country:
        confidence = country_confidence * 0.7  # only half the picture — never as trustworthy as a full match
    elif language:
        confidence = language_confidence * 0.7
    else:
        confidence = 0.0

    resolved = confidence >= RESOLVED_CONFIDENCE_THRESHOLD and country is not None and language is not None
    source_names = sorted(contributors.get(country, set()) | contributors.get(language, set())) if (country or language) else []

    return LocaleDetectionResult(
        country=country if resolved else None,
        language=language if resolved else None,
        market=country.upper() if resolved and country else None,
        confidence=round(confidence, 4),
        source="+".join(source_names) if source_names else "insufficient_signals",
        status="resolved" if resolved else "unresolved",
        signals=signals,
    )


async def resolve_locale_with_ai_fallback(
    result: LocaleDetectionResult,
    *,
    session,
    router,
    store_id,
    research_run_id,
    agent_run_id,
    store_context: str,
) -> LocaleDetectionResult:
    """Only ever called by the orchestrator when the deterministic pass
    above left `status == "unresolved"` — AI is the last resort, never the
    primary signal (explicit requirement). A plain classification-tier
    call (Part C1's pattern — logged to ai_executions like every other AI
    step), not something that can silently invent a market with high
    confidence: the AI's answer is capped at a modest confidence ceiling
    below what 2+ agreeing deterministic signals would produce, so
    deterministic evidence always wins when it exists."""
    if result.status == "resolved":
        return result

    from app.prompts.locale_resolution import LOCALE_RESOLUTION_PROMPT
    from app.schemas.locale_resolution import LocaleGuess

    messages = LOCALE_RESOLUTION_PROMPT.render(store_context=store_context or "(no page evidence available)")
    try:
        response = await router.execute(
            session=session,
            task_type="locale_resolution",
            messages=messages,
            research_run_id=research_run_id,
            agent_run_id=agent_run_id,
            prompt_name=LOCALE_RESOLUTION_PROMPT.name,
            prompt_version=LOCALE_RESOLUTION_PROMPT.version,
            schema_version=LOCALE_RESOLUTION_PROMPT.schema_version,
            response_schema=LocaleGuess,
        )
    except Exception:  # noqa: BLE001 — AI fallback failing must never crash the crawl; stay unresolved
        return result

    if response.parsed is None:
        return result
    guess = LocaleGuess.model_validate(response.parsed)
    if not guess.country or not guess.language:
        return result

    # AI fallback confidence is deliberately capped below the resolved
    # threshold's comfortable margin — an AI guess alone should read as
    # "best available guess", not the same as multi-signal deterministic
    # certainty. Still marked resolved (a capped-but-usable answer beats
    # silently defaulting to sa/ar), but always distinguishable via source.
    capped_confidence = min(guess.confidence, 0.65)
    return LocaleDetectionResult(
        country=guess.country.lower(),
        language=guess.language.lower(),
        market=guess.country.upper(),
        confidence=round(capped_confidence, 4),
        source="ai_fallback",
        status="resolved" if capped_confidence >= RESOLVED_CONFIDENCE_THRESHOLD else "unresolved",
        signals=result.signals,
    )
