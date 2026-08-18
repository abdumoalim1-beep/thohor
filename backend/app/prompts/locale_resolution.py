from app.prompts.base import PromptTemplate

LOCALE_RESOLUTION_PROMPT = PromptTemplate(
    name="locale_resolution",
    version="v1",
    schema_version="v1",
    system=(
        "You classify the real-world target market and language of an online store from "
        "page evidence. Only ever used as a last resort when deterministic signals (domain, "
        "currency, hreflang, HTML lang, address data) were insufficient — do not assume a "
        "default market when the evidence is genuinely ambiguous; say so via a low confidence.\n\n"
        "Return raw JSON only — no Markdown, no ``` fences, no text before or after — matching "
        "exactly these field names:\n"
        "{\n"
        '  "country": "us",\n'
        '  "language": "en",\n'
        '  "confidence": 0.0\n'
        "}\n"
        "country is a lowercase ISO 3166-1 alpha-2 code. language is a lowercase ISO 639-1 code. "
        "confidence is 0 to 1, reflecting how certain you are from the evidence given, not how "
        "certain you generally feel."
    ),
    user_template=(
        "Deterministic signals already gathered for this store (may be empty or conflicting):\n\n"
        "{store_context}\n\n"
        "What is this store's most likely target country and language?"
    ),
)
