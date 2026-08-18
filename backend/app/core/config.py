from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.evaluation_mode import EvaluationMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    cors_allowed_origins: list[str] = ["http://localhost:3000"]

    # Evaluation mode (post-G-B directive) — controls how SERP/AI-visibility
    # data is sourced during development and evaluation runs. Defaults to
    # replay: real historical data, zero new network calls, never silently
    # mock. See app/core/evaluation_mode.py.
    evaluation_mode: EvaluationMode = EvaluationMode.replay

    # Hard guard on real SerpAPI spend outside an approved evaluation
    # campaign (Part H3). 0 = no live SerpAPI calls permitted at all; a
    # developer must explicitly raise this (or set live_serp_override) to
    # spend real search credits — never happens by accident.
    dev_live_serp_budget: int = 0
    live_serp_override: bool = False
    max_live_serp_requests_per_campaign: int = 250
    max_live_serp_requests_per_run: int = 30

    # Concurrency ceilings — independent tasks run in parallel up to these
    # limits instead of strictly sequentially; each provider gets its own
    # limit rather than one global semaphore, since SerpAPI/OpenAI/crawler
    # all have different real-world rate tolerances.
    research_max_concurrency: int = 5
    store_run_max_concurrency: int = 2
    serp_max_concurrency: int = 3
    ai_max_concurrency: int = 5
    crawl_max_concurrency: int = 5
    page_analysis_max_concurrency: int = 3

    # Database
    database_url: str = "postgresql+psycopg://mersad:mersad@localhost:5432/mersad"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Object storage (MinIO, S3-compatible)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "mersad"
    s3_secret_key: SecretStr = SecretStr("mersad_local_dev")
    s3_bucket_raw_artifacts: str = "raw-artifacts"

    # AI providers — absent keys simply disable that provider at router init
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None

    # Crawler
    crawler_initial_pages_per_run: int = 20
    crawler_fast_max_pages: int = 10
    crawler_fast_min_pages: int = 6
    crawler_fast_timeout_seconds: float = 90.0
    crawler_fast_concurrency: int = 3
    crawler_max_pages_per_run: int = 100
    crawler_max_depth: int = 5
    # Playwright is far more expensive per page than the plain httpx fetch
    # — bounded per crawl so a heavily-blocked site can't turn a single
    # onboarding scan into dozens of headless-browser launches.
    crawler_playwright_max_fallbacks: int = 5
    crawler_request_timeout_seconds: float = 10.0
    crawler_max_response_bytes: int = 5_000_000
    # Phase 4 — cap on how many identity-based competitor suggestions a
    # single web_search call is allowed to persist per store per run.
    competitor_discovery_max_suggestions: int = 10
    crawler_user_agent: str = "MersadBot/0.1 (+https://mersad.example/bot)"

    # SERP provider — absent key falls back to the mock provider
    serpapi_api_key: SecretStr | None = None
    serp_default_country: str = "sa"
    serp_default_language: str = "ar"
    serp_num_results: int = 20

    # Intent & SERP budget caps (cost control — applies even with mock providers)
    # A useful market map needs breadth across categories. The basic store
    # understanding still appears first; these searches continue afterward.
    intent_max_per_run: int = 80
    serp_max_queries_per_run: int = 60

    # AI Visibility Test Matrix budget caps — real AI providers, real cost
    # from the first run (unlike SERP, which falls back to mock without a
    # key). Keep these conservative: intents × prompts × engines ×
    # repetitions multiplies fast.
    ai_visibility_max_intents_per_run: int = 5
    ai_visibility_prompt_variants_per_intent: int = 5
    ai_visibility_repetitions: int = 2

    # Page Intelligence — caps how many competitor pages get crawled + AI
    # gap-analyzed per run (each one is a real crawl + a real AI call).
    page_intelligence_max_gaps_per_run: int = 3

    # Iterative Research Orchestrator (Group D2) — hard ceilings for the
    # research_tasks loop across every dimension it can consume. The loop
    # stops the moment any one of these is hit (app/research/budget.py),
    # regardless of how many pending tasks the Planner still wants to run.
    research_max_search_requests: int = 100
    research_max_ai_requests: int = 100
    research_max_pages: int = 30
    research_max_tokens: int = 500_000
    research_max_cost_usd: float = 2.0
    research_max_duration_seconds: float = 600.0
    research_max_depth: int = 3
    research_max_tasks: int = 80

    # Opportunity/Recommendation Engine (Group E) — detectors are free
    # (no AI/network calls), so opportunity discovery itself is uncapped;
    # these only bound how many become customer-facing Recommendations and
    # how many sit in the "Do Now" primary queue vs backlog (Part E8).
    recommendation_max_per_run: int = 10
    recommendation_primary_queue_size: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
