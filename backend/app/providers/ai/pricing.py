"""Per-1K-token USD pricing used only to populate ai_executions.cost_usd for
budget tracking. Approximate on purpose — this is cost *visibility*, not a
billing system. Update as providers change pricing; unknown models default
to 0.0 so a missing price never crashes a research run.
"""

_PRICING_PER_1K_TOKENS: dict[str, dict[str, tuple[float, float]]] = {
    "openai": {
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-4o": (0.0025, 0.01),
    },
    "anthropic": {
        "claude-haiku-4-5-20251001": (0.001, 0.005),
        "claude-sonnet-4-5-20250929": (0.003, 0.015),
    },
    "google": {
        "gemini-2.5-flash": (0.000075, 0.0003),
        "gemini-2.5-pro": (0.00125, 0.005),
    },
    "mock": {},
}


def estimate_cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = _PRICING_PER_1K_TOKENS.get(provider, {}).get(model, (0.0, 0.0))
    return round((input_tokens / 1000) * input_price + (output_tokens / 1000) * output_price, 6)
