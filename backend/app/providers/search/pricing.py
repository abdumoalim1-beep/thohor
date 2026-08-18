"""Per-search USD pricing used only to populate serp_executions.cost_usd for
budget/cost visibility — mirrors app/providers/ai/pricing.py's philosophy
exactly: approximate on purpose, cost *visibility* not a billing system.
Unknown providers default to 0.0 so a missing price never crashes a run.
"""

# SerpApi's standard plan works out to roughly $0.01/search (varies by plan
# tier) — a documented approximation, not pulled from a live billing API.
_PRICE_PER_SEARCH_USD: dict[str, float] = {
    "serpapi": 0.01,
    "mock": 0.0,
}


def estimate_search_cost_usd(provider: str) -> float:
    return _PRICE_PER_SEARCH_USD.get(provider, 0.0)
