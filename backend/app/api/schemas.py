import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateStoreRequest(BaseModel):
    url: str
    country: str | None = None
    language: str | None = None
    organization_id: uuid.UUID | None = None


class CreateStoreResponse(BaseModel):
    store_id: uuid.UUID
    research_run_id: uuid.UUID
    status: str


class CancelResearchRunResponse(BaseModel):
    research_run_id: uuid.UUID
    cancellation_requested: bool


class AgentRunSummary(BaseModel):
    agent_type: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    findings: dict | None = None
    error: str | None = None


class ResearchRunSummary(BaseModel):
    id: uuid.UUID
    run_type: str
    status: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    agent_runs: list[AgentRunSummary] = Field(default_factory=list)


class VisibilitySummary(BaseModel):
    total_intents_measured: int
    ranking_coverage: float
    top3_rate: float
    top10_rate: float
    avg_client_rank: float | None = None


class AIVisibilitySummary(BaseModel):
    total_observations: int
    mention_rate: float
    intent_coverage: float
    citation_rate: float
    stability: float


class SurfaceMetrics(BaseModel):
    surface: str
    total_observations: int
    mention_rate: float
    intent_coverage: float
    citation_rate: float
    stability: float
    # Capability transparency (Part F.5-14) — whether this surface's probes
    # used web search/grounding, so a mention rate is never misread as
    # "grounded AI search visibility" when it's really base-model knowledge.
    search_enabled: bool = False
    grounding_enabled: bool = False


class CrossSurfaceIntentItem(BaseModel):
    stable_intent_id: uuid.UUID
    topic: str
    store_visibility: dict[str, float] = Field(default_factory=dict)
    competitor_visibility: dict[str, dict[str, float]] = Field(default_factory=dict)
    # Part R6 — domain -> classification (e.g. "direct_competitor",
    # "publisher", "marketplace", ...), so the frontend can frame a domain
    # that out-ranks the store honestly (an insight about the query, e.g.
    # Wikipedia answering an informational intent) instead of implying
    # every domain in competitor_visibility is a business rival.
    competitor_classifications: dict[str, str] = Field(default_factory=dict)


class CrossSurfaceVisibilityResponse(BaseModel):
    intents: list[CrossSurfaceIntentItem] = Field(default_factory=list)
    # Same "unavailable != zero" rule as AIVisibilityListResponse — a
    # surface listed here is absent from every intent's store_visibility/
    # competitor_visibility dicts on purpose, never present with a 0.0.
    unavailable_surfaces: list[str] = Field(default_factory=list)


class SurfaceUsageItem(BaseModel):
    surface: str
    requests: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float


class CostSummaryResponse(BaseModel):
    google: SurfaceUsageItem
    ai_surfaces: list[SurfaceUsageItem] = Field(default_factory=list)
    unavailable_surfaces: list[str] = Field(default_factory=list)
    other_ai_cost_usd: float
    total_cost_usd: float


class ResearchSummary(BaseModel):
    total_tasks: int
    search_queries_executed: int
    ai_conversations_executed: int
    pages_crawled: int
    competitor_pages_analyzed: int
    competitors_discovered: int
    intents_discovered: int
    new_queries_discovered: int
    findings_generated: int
    findings_validated: int
    evidence_records: int
    total_tokens: int
    total_cost_usd: float
    duration_seconds: float
    research_depth_reached: int


class StoreProfileProduct(BaseModel):
    name: str
    url: str
    image_url: str | None = None


class StoreProfileCategory(BaseModel):
    name: str
    url: str | None = None


class StoreProfile(BaseModel):
    name: str
    domain: str
    title: str | None = None
    description: str | None = None
    country: str | None = None
    language: str | None = None
    locale_status: str
    locale_confidence: float | None = None
    platform: str | None = None
    business_type: str | None = None
    classification_confidence: float | None = None
    primary_categories: list[str] = Field(default_factory=list)
    products_count: int | None = None
    categories_count: int | None = None
    brands_count: int | None = None
    pages_count: int
    page_type_counts: dict[str, int] = Field(default_factory=dict)
    products: list[StoreProfileProduct] = Field(default_factory=list)
    categories: list[StoreProfileCategory] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list)


class TopCategoryItem(BaseModel):
    id: uuid.UUID
    name: str
    product_count: int


class ProductSampleItem(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    category_name: str | None = None
    price: float | None = None
    currency: str | None = None
    image_url: str | None = None
    detail_available: bool = True


class ProductCategoryPreviewItem(BaseModel):
    name: str
    image_url: str | None = None
    url: str | None = None
    product_count: int | None = None
    confidence: float | None = None
    source: str  # catalog | classification


class BusinessInfoItem(BaseModel):
    kind: str
    label: str
    url: str


class BrandItem(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    # True when this name was inferred from the domain rather than found in
    # structured page data — the frontend must never present a guess as a
    # confirmed fact.
    is_guessed: bool = False


class BrandNameConfirmRequest(BaseModel):
    name: str


class BrandNameConfirmResponse(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)


class SuggestedCompetitorItem(BaseModel):
    """Phase 4 — a competitor found via identity-based web search, awaiting
    user confirmation (or already auto-confirmed on strong evidence).
    Deliberately separate from CompetitorListItem (SERP/AI-visibility
    ranking): these have no CompetitorRelationship rows and no rank/citation
    counts, only a confirmation_status the user can act on."""

    id: uuid.UUID
    domain: str
    name: str
    confirmation_status: str  # pending_user_confirmation|auto_confirmed|user_confirmed|user_rejected
    classification_confidence: float | None = None
    discovery_reason: str | None = None


class StoreUnderstandingResponse(BaseModel):
    # Legacy stages (still returned when no store_identity_agent_run exists
    # for this run, e.g. old runs predating identity decoupling): "pending"
    # = crawl not yet finished; "partial" = crawl done, classification
    # still running or failed; "ready" = crawl + classification both
    # completed with a confident result; "low_confidence" = classification
    # was skipped or below the confidence floor; "failed" = crawl itself
    # failed.
    #
    # New stages (once identity resolution has run for this store):
    # "resolving_identity" = identity search in progress; "provisional" =
    # brand name + activity resolved well enough to complete registration,
    # catalog scan not started yet; "catalog_scanning" = identity resolved,
    # products being extracted in background; "ready" = identity resolved
    # AND catalog scan completed; "needs_confirmation" = a plausible
    # identity exists but below the confidence bar — user must confirm/
    # edit, never a hard wall; "catalog_blocked" = identity resolved fine
    # but product extraction failed/was blocked — registration can still
    # proceed; "failed" = even identity resolution failed.
    understanding_stage: str
    display_name: str | None = None
    description: str | None = None
    url: str
    business_type: str | None = None
    # From StoreIdentity's web-search resolution when available — "السوق
    # والدولة والمدينة عند توفرها" for the /signup identity screen.
    country: str | None = None
    city: str | None = None
    primary_categories: list[str] = Field(default_factory=list)
    target_audience: list[str] = Field(default_factory=list)
    classification_confidence: float | None = None
    classification_skipped: bool = False
    # "web_search" | "crawl" | None — which source produced the identity
    # currently shown (business_type/display_name above may be sourced
    # from either, see get_store_understanding's fill-gaps-only merge).
    identity_source: str | None = None
    identity_confidence: float | None = None
    catalog_status: str = "pending"  # pending|scanning|ready|partial|blocked|failed
    catalog_products_found: int = 0
    competitor_discovery_status: str = "pending"  # pending|running|completed|failed
    suggested_competitors: list[SuggestedCompetitorItem] = Field(default_factory=list)
    pages_crawled: int
    products_found: int
    categories_found: int
    brands_found: int
    top_categories: list[TopCategoryItem] = Field(default_factory=list)
    product_samples: list[ProductSampleItem] = Field(default_factory=list)
    category_previews: list[ProductCategoryPreviewItem] = Field(default_factory=list)
    product_count_status: str = "unavailable"  # confirmed | estimated | unavailable
    estimated_products_count: int | None = None
    sold_brands: list[str] = Field(default_factory=list)
    business_info: list[BusinessInfoItem] = Field(default_factory=list)
    audience_basis: str | None = None
    brand: BrandItem | None = None
    last_analyzed_at: str | None = None


class CompetitorConfirmationRequest(BaseModel):
    action: str  # "confirm" | "reject"


class StoreFeedbackRequest(BaseModel):
    feedback_type: str  # "confirmed" | "incorrect"
    issues: list[str] = Field(default_factory=list)
    note: str | None = None


class StoreFeedbackResponse(BaseModel):
    id: uuid.UUID
    feedback_type: str
    issues: list[str] = Field(default_factory=list)
    note: str | None = None
    created_at: str


class ProductDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    category_name: str | None = None
    price: float | None = None
    currency: str | None = None
    availability: str | None = None
    image_url: str | None = None


class ProductPageCheckItem(BaseModel):
    key: str
    label: str
    status: str
    current_value: str | None = None
    message: str


class ProductImageInsightItem(BaseModel):
    url: str
    alt: str | None = None
    width: int | None = None
    height: int | None = None
    issues: list[str] = Field(default_factory=list)
    status: str


class OptimizeProductImageRequest(BaseModel):
    image_url: str
    quality: int = Field(default=82, ge=50, le=95)


class OptimizeProductImageResponse(BaseModel):
    original_bytes: int
    optimized_bytes: int
    saved_percent: float
    width: int
    height: int
    download_url: str


class ProductWorkspaceRecommendationItem(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    link_basis: str
    implementation: dict = Field(default_factory=dict)


class ProductWorkspaceItem(ProductDetailResponse):
    completion_score: int
    issues_count: int
    observed_at: str | None = None


class ProductWorkspaceListResponse(BaseModel):
    products: list[ProductWorkspaceItem] = Field(default_factory=list)


class CategoryWorkspaceItem(BaseModel):
    id: uuid.UUID
    page_id: uuid.UUID | None = None
    name: str
    url: str | None = None
    product_count: int
    representative_image_url: str | None = None
    confidence: float = 1.0
    observed_at: str | None = None


class CategoryWorkspaceListResponse(BaseModel):
    categories: list[CategoryWorkspaceItem] = Field(default_factory=list)


class PageWorkspaceItem(BaseModel):
    id: uuid.UUID
    url: str
    page_type: str
    title: str | None = None
    h1: str | None = None
    image_url: str | None = None
    completion_score: int
    issues_count: int
    observed_at: str | None = None


class PageWorkspaceListResponse(BaseModel):
    pages: list[PageWorkspaceItem] = Field(default_factory=list)


class PageWorkspaceResponse(PageWorkspaceItem):
    current: dict = Field(default_factory=dict)
    checks: list[ProductPageCheckItem] = Field(default_factory=list)
    recommendations: list[ProductWorkspaceRecommendationItem] = Field(default_factory=list)


class CapturePageScreenshotRequest(BaseModel):
    mobile: bool = False


class CapturePageScreenshotResponse(BaseModel):
    screenshot_url: str
    mobile: bool
    width: int
    height: int
    annotations: list[dict] = Field(default_factory=list)


class ProductWorkspaceResponse(ProductDetailResponse):
    observed_at: str | None = None
    current: dict = Field(default_factory=dict)
    checks: list[ProductPageCheckItem] = Field(default_factory=list)
    image_insights: list[ProductImageInsightItem] = Field(default_factory=list)
    completion_score: int
    recommendations: list[ProductWorkspaceRecommendationItem] = Field(default_factory=list)


class ComponentSnapshotItem(BaseModel):
    research_run_id: uuid.UUID
    status: str
    progress_completed: int
    progress_total: int
    payload: dict
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class StoreDetailResponse(BaseModel):
    id: uuid.UUID
    url: str
    status: str
    pages_crawled: int
    products_found: int
    categories_found: int
    total_ai_cost_usd: float
    intents_found: int
    total_serp_cost_usd: float
    competitors_found: int
    visibility_summary: VisibilitySummary | None = None
    ai_visibility_summary: AIVisibilitySummary | None = None
    research_summary: ResearchSummary | None = None
    store_profile: StoreProfile | None = None
    latest_run: ResearchRunSummary | None = None
    component_snapshots: dict[str, ComponentSnapshotItem] = Field(default_factory=dict)


class IntentKeywordItem(BaseModel):
    text: str
    is_primary: bool


class IntentListItem(BaseModel):
    id: uuid.UUID
    topic: str
    category: str | None = None
    commercial_stage: str | None = None
    estimated_demand: str | None = None
    confidence: float
    source: str
    keywords: list[IntentKeywordItem] = Field(default_factory=list)
    client_rank: int | None = None
    client_url: str | None = None
    search_status: str = "not_tested"
    search_results_count: int | None = None
    search_observed_at: str | None = None
    search_country: str | None = None
    search_device: str | None = None
    search_engine: str | None = None


class IntentListResponse(BaseModel):
    intents: list[IntentListItem] = Field(default_factory=list)


class IntentClusterItem(BaseModel):
    id: uuid.UUID
    label: str
    category: str | None = None
    intent_count: int
    intent_topics: list[str] = Field(default_factory=list)


class IntentClusterListResponse(BaseModel):
    clusters: list[IntentClusterItem] = Field(default_factory=list)


class AIVisibilityObservationItem(BaseModel):
    id: uuid.UUID
    intent_topic: str
    prompt_text: str
    surface: str
    provider: str
    model: str
    search_enabled: bool = False
    grounding_enabled: bool = False
    citations_available: bool = False
    repetition_index: int = 0
    observed_at: datetime | None = None
    mentioned: bool
    mention_position: int | None = None
    competitors_mentioned: list[str] = Field(default_factory=list)
    products_mentioned: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    linked_domains: list[str] = Field(default_factory=list)
    cited_domains: list[str] = Field(default_factory=list)
    response_text: str | None = None


class AIVisibilityListResponse(BaseModel):
    summary: AIVisibilitySummary
    by_surface: list[SurfaceMetrics] = Field(default_factory=list)
    # Surfaces with no API key configured at all — never folded into
    # `summary`/`by_surface` as a 0%. Distinct from a configured surface
    # that simply had zero observations this run.
    unavailable_surfaces: list[str] = Field(default_factory=list)
    observations: list[AIVisibilityObservationItem] = Field(default_factory=list)


class CompetitorListItem(BaseModel):
    id: uuid.UUID
    domain: str
    name: str
    competitor_type: str
    serp_appearances: int
    avg_serp_rank: float | None = None
    ai_citation_count: int
    # Part G-B2 — business-relevance classification, distinct from
    # competitor_type (discovery mechanism). is_business_competitor is the
    # one flag the UI should use to decide "show as a direct competitor".
    classification: str
    relevance_score: float
    classification_confidence: float
    discovery_reason: str | None = None
    shared_stable_intents_count: int
    is_business_competitor: bool


class CompetitorListResponse(BaseModel):
    competitors: list[CompetitorListItem] = Field(default_factory=list)
    direct_competitor_count: int = 0
    visibility_only_count: int = 0


class PageGapItem(BaseModel):
    id: uuid.UUID
    intent_topic: str
    competitor_domain: str
    competitor_url: str
    gaps: list[str] = Field(default_factory=list)
    recommendation_summary: str
    confidence: float | None = None


class PageGapListResponse(BaseModel):
    page_gaps: list[PageGapItem] = Field(default_factory=list)


class ResearchTaskItem(BaseModel):
    id: uuid.UUID
    parent_task_id: uuid.UUID | None = None
    task_type: str
    status: str
    depth: int
    priority: float
    reason: str | None = None
    hypothesis: str | None = None
    result_summary: str | None = None
    discovered_entities: dict = Field(default_factory=dict)
    created_tasks_count: int
    cost: float | None = None


class ResearchTaskListResponse(BaseModel):
    tasks: list[ResearchTaskItem] = Field(default_factory=list)


class FindingItem(BaseModel):
    id: uuid.UUID
    finding_type: str
    statement: str
    confidence: float
    status: str
    validation_count: int
    affected_competitors: list[str] = Field(default_factory=list)
    affected_intents: list[str] = Field(default_factory=list)


class FindingListResponse(BaseModel):
    findings: list[FindingItem] = Field(default_factory=list)


class OpportunityItem(BaseModel):
    id: uuid.UUID
    opportunity_type: str
    title: str
    description: str
    priority_score: float
    score_breakdown: dict = Field(default_factory=dict)
    confidence: float
    effort_estimate: str
    status: str
    affected_intents: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)


class OpportunityListResponse(BaseModel):
    opportunities: list[OpportunityItem] = Field(default_factory=list)


class RecommendationItem(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    opportunity_type: str
    title: str
    what_we_found: str = ""
    what_to_do: str
    why_it_matters: str
    why_this_improvement: str = ""
    target_page: str | None = None
    target_intents: list[str] = Field(default_factory=list)
    expected_impact: float
    confidence: float
    confidence_tier: str = "medium"
    claim_basis: str = "observed_with_best_practice"
    effort_estimate: str
    priority_score: float
    status: str
    is_primary: bool
    freshness: str
    implementation_url: str | None = None
    implemented_at: str | None = None


class RecommendationListResponse(BaseModel):
    recommendations: list[RecommendationItem] = Field(default_factory=list)


class CompetitorReferenceItem(BaseModel):
    """Part R6 — resolves a competitor UUID (what Recommendation.
    competitors_reference stores) to something a user can actually read:
    domain/name plus its business-relevance classification, so the UI never
    has to show a raw ID or imply every referenced competitor is a direct
    business rival."""

    id: uuid.UUID
    domain: str
    name: str
    classification: str
    is_business_competitor: bool


class RecommendationDetail(RecommendationItem):
    implementation_steps: list[str] = Field(default_factory=list)
    measurement_plan: dict = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    competitors_reference: list[CompetitorReferenceItem] = Field(default_factory=list)


class UpdateRecommendationStatusRequest(BaseModel):
    status: str
    implementation_url: str | None = None


class SaveImplementationDraftRequest(BaseModel):
    fields: dict = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    id: uuid.UUID
    source_type: str
    confidence: float | None = None
    summary: str | None = None


class RecommendationFindingItem(BaseModel):
    id: uuid.UUID
    finding_type: str
    statement: str
    confidence: float
    status: str


class RecommendationEvidenceResponse(BaseModel):
    opportunity: OpportunityItem | None = None
    findings: list[RecommendationFindingItem] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ImplementationPackageResponse(BaseModel):
    implementation_package: dict = Field(default_factory=dict)


class AlertItem(BaseModel):
    id: uuid.UUID
    alert_type: str
    severity: str
    title: str
    message: str
    status: str
    related_recommendation_id: uuid.UUID | None = None
    related_competitor_id: uuid.UUID | None = None
    created_at: str


class AlertListResponse(BaseModel):
    alerts: list[AlertItem] = Field(default_factory=list)


class UpdateAlertStatusRequest(BaseModel):
    status: str


class OnboardingStageMetric(BaseModel):
    """Real per-commercial-stage counts from the accepted/measured intent
    set — never a made-up split. `measured` is how many accepted intents in
    this stage have at least one SERP observation; `top10` is how many of
    those the store itself ranked in the top 10 for."""

    stage: str
    measured: int
    top10: int


class OnboardingSampleIntent(BaseModel):
    """One real measured intent, annotated with the strongest real
    competitor (if any) that also appeared in that same SERP observation —
    powers the onboarding wizard's 'تظهر / لا تظهر / يظهر منافس' badge."""

    topic: str
    commercial_stage: str | None = None
    client_rank: int | None = None
    top_competitor_domain: str | None = None
    top_competitor_name: str | None = None
    top_competitor_rank: int | None = None


class OnboardingCompetitorSummary(BaseModel):
    domain: str
    name: str
    serp_appearances: int
    sample_appearances: int
    # The commercial_stage where this competitor's real SERP appearances
    # concentrate most, if any single stage is a clear majority — never a
    # guess when the split is even or the competitor has too few
    # appearances to say anything meaningful.
    stronger_stage: str | None = None


class OnboardingSummaryResponse(BaseModel):
    """Aggregated purely from data the pipeline already measured this run
    (Intent + SerpObservation + CompetitorRelationship) — no new AI or SERP
    calls. Powers the /signup onboarding wizard's result/competitors/market
    steps without re-deriving scoring logic that lives elsewhere."""

    measured_count: int
    sample_size: int
    store_sample_appearances: int
    best_rank: int | None = None
    stage_breakdown: list[OnboardingStageMetric] = Field(default_factory=list)
    top_competitors: list[OnboardingCompetitorSummary] = Field(default_factory=list)
    sample_intents: list[OnboardingSampleIntent] = Field(default_factory=list)
    products_found: int = 0
    categories_found: int = 0

    # AI-visibility measurement — fully additive alongside the Google/SERP
    # fields above (never derived from or blended into them). Zero means
    # "not measured yet this run", not "zero mentions" — the frontend must
    # only show a result once measured_count > 0.
    ai_measured_count: int = 0
    ai_sample_size: int = 0
    ai_store_sample_appearances: int = 0


class OnboardingLeadRequest(BaseModel):
    name: str
    contact: str


class OnboardingLeadResponse(BaseModel):
    id: uuid.UUID
    store_id: uuid.UUID
    name: str
    contact: str
    created_at: str


class TriggerVisibilityRunResponse(BaseModel):
    # None + status="not_ready" when no VisibilityQuestion rows exist yet
    # for the store (question generation is a later step inside the same
    # baseline research run, after identity resolution) — no run is
    # created in that case, so the caller can safely retry shortly instead
    # of getting a wasted run that would've completed instantly with 0
    # questions measured.
    visibility_run_id: uuid.UUID | None = None
    status: str


class VisibilitySourceItem(BaseModel):
    url: str
    title: str
    source_type: str  # official_store|competitor_store|marketplace|social|forum|video|publisher|other|...


class VisibilityCompetitorMentionItem(BaseModel):
    name: str
    rank: int | None = None


class VisibilityAnswerItem(BaseModel):
    engine: str
    status: str
    raw_answer: str | None = None
    brand_mentioned: bool | None = None
    mention_type: str | None = None
    mention_rank: int | None = None
    recommendation_rank: int | None = None
    evidence_quote: str | None = None
    competitors_mentioned: list[VisibilityCompetitorMentionItem] = Field(default_factory=list)
    sources: list[VisibilitySourceItem] = Field(default_factory=list)


class VisibilityQuestionItem(BaseModel):
    question_id: uuid.UUID
    text: str
    category: str
    answers: list[VisibilityAnswerItem] = Field(default_factory=list)


class VisibilityMetricsSummary(BaseModel):
    successful_answers: int
    mention_rate: float | None = None
    recommendation_rate: float | None = None
    avg_recommendation_rank: float | None = None
    top_3_rate: float | None = None
    share_of_voice: float | None = None
    citation_rate: float | None = None
    top_competitor: str | None = None
    top_competitor_mentions: int = 0
    week_over_week: dict | None = None


class VisibilityCompetitorSummaryItem(BaseModel):
    name: str
    mentions: int


class VisibilitySourceSummaryItem(BaseModel):
    url: str
    title: str
    source_type: str
    count: int


class VisibilityTopCompetitorItem(BaseModel):
    """SIGNUP re-scope — the richer top-5 shape /signup's report needs.
    Additive alongside VisibilityCompetitorSummaryItem (kept for the
    existing ai-answers dashboard, unchanged)."""

    name: str
    domain: str | None = None
    appearances: int
    appearance_rate: float
    avg_rank: float | None = None
    ahead_of_client: bool


class VisibilityOpportunityItem(BaseModel):
    title: str
    reason: str
    evidence: str
    actions: list[str] = Field(default_factory=list)


class VisibilityCitationItem(BaseModel):
    domain: str
    citation_count: int
    supports: str  # "client" | "competitor" | "mixed"


class VisibilitySignupReport(BaseModel):
    """SIGNUP re-scope — one merged, engine-agnostic report block for the
    /signup journey. `engine` stays on the underlying rows/`sources`/
    `questions` fields for internal audit only; nothing here is split by
    chatgpt/google."""

    total_searches: int
    mentioned_count: int
    appearance_rate: float | None = None
    avg_rank: float | None = None
    top3_count: int
    competitors_ahead_count: int
    # "ترتيب ظهور علامتك بين أبرز المنافسين: X من Y" — client_rank is 1
    # when it appears more than any competitor, competitors_considered_count
    # is how many entities (client + competitors) were actually compared.
    client_rank: int | None = None
    competitors_considered_count: int = 0
    top_competitors: list[VisibilityTopCompetitorItem] = Field(default_factory=list)
    citations: list[VisibilityCitationItem] = Field(default_factory=list)
    opportunities: list[VisibilityOpportunityItem] = Field(default_factory=list)


class VisibilityRunDetailResponse(BaseModel):
    run_id: uuid.UUID | None = None
    status: str  # no_run_yet|running|completed|failed
    started_at: str | None = None
    completed_at: str | None = None
    engines_attempted: list[str] = Field(default_factory=list)
    summary: VisibilityMetricsSummary | None = None
    questions: list[VisibilityQuestionItem] = Field(default_factory=list)
    competitors: list[VisibilityCompetitorSummaryItem] = Field(default_factory=list)
    sources: list[VisibilitySourceSummaryItem] = Field(default_factory=list)
    report: VisibilitySignupReport | None = None
    # Live-progress fields — populated while status=="running" so the
    # unified "تحليل ظهور علامتك" screen can show a real X/90 counter
    # without waiting for the full report assembly below (which isn't
    # meaningful yet mid-run anyway).
    completed_count: int | None = None
    total_planned: int | None = None
