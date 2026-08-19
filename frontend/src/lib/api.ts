const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export type AgentRunSummary = {
  agent_type: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  findings: Record<string, unknown> | null;
  error: string | null;
};

export type ResearchRunSummary = {
  id: string;
  run_type: string;
  status: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  agent_runs: AgentRunSummary[];
};

export type VisibilitySummary = {
  total_intents_measured: number;
  ranking_coverage: number;
  top3_rate: number;
  top10_rate: number;
  avg_client_rank: number | null;
};

export type AIVisibilitySummary = {
  total_observations: number;
  mention_rate: number;
  intent_coverage: number;
  citation_rate: number;
  stability: number;
};

export type ResearchSummary = {
  total_tasks: number;
  search_queries_executed: number;
  ai_conversations_executed: number;
  pages_crawled: number;
  competitor_pages_analyzed: number;
  competitors_discovered: number;
  intents_discovered: number;
  new_queries_discovered: number;
  findings_generated: number;
  findings_validated: number;
  evidence_records: number;
  total_tokens: number;
  total_cost_usd: number;
  duration_seconds: number;
  research_depth_reached: number;
};

export type StoreProfileProduct = { name: string; url: string; image_url: string | null };
export type StoreProfileCategory = { name: string; url: string | null };

export type StoreProfile = {
  name: string;
  domain: string;
  title: string | null;
  description: string | null;
  country: string | null;
  language: string | null;
  locale_status: string;
  locale_confidence: number | null;
  platform: string | null;
  business_type: string | null;
  classification_confidence: number | null;
  primary_categories: string[];
  products_count: number | null;
  categories_count: number | null;
  brands_count: number | null;
  pages_count: number;
  page_type_counts: Record<string, number>;
  products: StoreProfileProduct[];
  categories: StoreProfileCategory[];
  brands: string[];
};

export type StoreDetail = {
  id: string;
  url: string;
  status: string;
  pages_crawled: number;
  products_found: number;
  categories_found: number;
  total_ai_cost_usd: number;
  intents_found: number;
  total_serp_cost_usd: number;
  competitors_found: number;
  visibility_summary: VisibilitySummary | null;
  ai_visibility_summary: AIVisibilitySummary | null;
  research_summary: ResearchSummary | null;
  store_profile: StoreProfile | null;
  latest_run: ResearchRunSummary | null;
  component_snapshots: Record<string, {
    research_run_id: string;
    status: "not_started" | "queued" | "running" | "partial" | "completed" | "failed" | "stale";
    progress_completed: number;
    progress_total: number;
    payload: Record<string, unknown>;
    started_at: string | null;
    completed_at: string | null;
    error: string | null;
  }>;
};

export type CreateStoreResponse = {
  store_id: string;
  research_run_id: string;
  status: string;
};

export type IntentKeywordItem = { text: string; is_primary: boolean };

export type IntentListItem = {
  id: string;
  topic: string;
  category: string | null;
  commercial_stage: string | null;
  estimated_demand: string | null;
  confidence: number;
  source: string;
  keywords: IntentKeywordItem[];
  client_rank: number | null;
  client_url: string | null;
  search_status?: "measured" | "failed" | "not_tested";
  search_results_count?: number | null;
  search_observed_at?: string | null;
  search_country?: string | null;
  search_device?: string | null;
  search_engine?: string | null;
};

export type AIVisibilityObservationItem = {
  id: string;
  intent_topic: string;
  prompt_text: string;
  surface: string;
  provider: string;
  model: string;
  search_enabled: boolean;
  grounding_enabled: boolean;
  citations_available: boolean;
  repetition_index: number;
  observed_at: string | null;
  mentioned: boolean;
  mention_position: number | null;
  competitors_mentioned: string[];
  products_mentioned: string[];
  citations: string[];
  linked_domains: string[];
  cited_domains: string[];
  response_text: string | null;
};

export type SurfaceMetrics = {
  surface: string;
  total_observations: number;
  mention_rate: number;
  intent_coverage: number;
  citation_rate: number;
  stability: number;
  search_enabled: boolean;
  grounding_enabled: boolean;
};

export type AIVisibilityListResponse = {
  summary: AIVisibilitySummary;
  by_surface: SurfaceMetrics[];
  // Surfaces with no API key at all — never a 0%, always explicit.
  unavailable_surfaces: string[];
  observations: AIVisibilityObservationItem[];
};

export type CrossSurfaceIntentItem = {
  stable_intent_id: string;
  topic: string;
  store_visibility: Record<string, number>;
  competitor_visibility: Record<string, Record<string, number>>;
  // Part R6 — domain -> classification, for every domain that also
  // appears in competitor_visibility.
  competitor_classifications: Record<string, string>;
};

export type CrossSurfaceVisibilityResponse = {
  intents: CrossSurfaceIntentItem[];
  unavailable_surfaces: string[];
};

export type SurfaceUsageItem = {
  surface: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
};

export type CostSummaryResponse = {
  google: SurfaceUsageItem;
  ai_surfaces: SurfaceUsageItem[];
  unavailable_surfaces: string[];
  other_ai_cost_usd: number;
  total_cost_usd: number;
};

export type CompetitorListItem = {
  id: string;
  domain: string;
  name: string;
  competitor_type: string;
  serp_appearances: number;
  avg_serp_rank: number | null;
  ai_citation_count: number;
  // Part G-B2/R6 — business-relevance classification, distinct from
  // competitor_type (discovery mechanism). is_business_competitor is the
  // one flag the UI should use to decide "show as a direct competitor".
  classification: string;
  relevance_score: number;
  classification_confidence: number;
  discovery_reason: string | null;
  shared_stable_intents_count: number;
  is_business_competitor: boolean;
};

export type OnboardingStageMetric = { stage: string; measured: number; top10: number };

export type OnboardingSampleIntent = {
  topic: string;
  commercial_stage: string | null;
  client_rank: number | null;
  top_competitor_domain: string | null;
  top_competitor_name: string | null;
  top_competitor_rank: number | null;
};

export type OnboardingCompetitorSummary = {
  domain: string;
  name: string;
  serp_appearances: number;
  sample_appearances: number;
  stronger_stage: string | null;
};

export type OnboardingSummary = {
  measured_count: number;
  sample_size: number;
  store_sample_appearances: number;
  best_rank: number | null;
  stage_breakdown: OnboardingStageMetric[];
  top_competitors: OnboardingCompetitorSummary[];
  sample_intents: OnboardingSampleIntent[];
  products_found: number;
  categories_found: number;
  ai_measured_count: number;
  ai_sample_size: number;
  ai_store_sample_appearances: number;
};

export type OnboardingLeadResponse = {
  id: string;
  store_id: string;
  name: string;
  contact: string;
  created_at: string;
};

export type PageGapItem = {
  id: string;
  intent_topic: string;
  competitor_domain: string;
  competitor_url: string;
  gaps: string[];
  recommendation_summary: string;
  confidence: number | null;
};

export type ResearchTaskItem = {
  id: string;
  parent_task_id: string | null;
  task_type: string;
  status: string;
  depth: number;
  priority: number;
  reason: string | null;
  hypothesis: string | null;
  result_summary: string | null;
  discovered_entities: Record<string, unknown>;
  created_tasks_count: number;
  cost: number | null;
};

export type FindingItem = {
  id: string;
  finding_type: string;
  statement: string;
  confidence: number;
  status: string;
  validation_count: number;
  affected_competitors: string[];
  affected_intents: string[];
};

export type OpportunityItem = {
  id: string;
  opportunity_type: string;
  title: string;
  description: string;
  priority_score: number;
  score_breakdown: Record<string, unknown>;
  confidence: number;
  effort_estimate: string;
  status: string;
  affected_intents: string[];
  competitors: string[];
};

export type RecommendationItem = {
  id: string;
  opportunity_id: string;
  opportunity_type: string;
  title: string;
  /** Beta Readiness Remediation, Section 5 structure: what_we_found is the
   * evidence-grounded observation; what_to_do/why_it_matters are the
   * existing action/impact copy; why_this_improvement is the explicit
   * reasoning link between what_we_found and what_to_do. */
  what_we_found: string;
  what_to_do: string;
  why_it_matters: string;
  why_this_improvement: string;
  target_page: string | null;
  target_intents: string[];
  expected_impact: number;
  confidence: number;
  /** Deterministic tier from evidence quantity/diversity/finding
   * validation (app.opportunities.confidence) — "low" never appears in the
   * primary queue. */
  confidence_tier: "high" | "medium" | "low";
  /** "observed" = the suggested action is itself directly evidenced;
   * "observed_with_best_practice" = the finding is evidenced but the
   * specific implementation detail is general best practice, not itself
   * evidence-derived; "unsupported" = generic-detector fallback only. */
  claim_basis: "observed" | "observed_with_best_practice" | "unsupported";
  effort_estimate: string;
  priority_score: number;
  status: string;
  is_primary: boolean;
  /** Part R2 — "current" (reconfirmed by the store's latest completed
   * run), "stale" (only an older run confirmed it), "historical"
   * (resolved: implemented/successful/dismissed/etc.), or "superseded". */
  freshness: "current" | "stale" | "historical" | "superseded";
  implementation_url: string | null;
  implemented_at: string | null;
};

/** Part R6 — a competitor UUID resolved to something a user can read:
 * domain/name plus its business-relevance classification, so the UI never
 * shows a raw ID or implies every referenced competitor is a direct rival. */
export type CompetitorReferenceItem = {
  id: string;
  domain: string;
  name: string;
  classification: string;
  is_business_competitor: boolean;
};

export type RecommendationDetail = RecommendationItem & {
  implementation_steps: string[];
  measurement_plan: Record<string, unknown>;
  evidence_ids: string[];
  competitors_reference: CompetitorReferenceItem[];
};

export type RecommendationFindingItem = {
  id: string;
  finding_type: string;
  statement: string;
  confidence: number;
  status: string;
};

export type EvidenceItem = {
  id: string;
  source_type: string;
  confidence: number | null;
  summary: string | null;
};

export type RecommendationEvidenceResponse = {
  opportunity: OpportunityItem | null;
  findings: RecommendationFindingItem[];
  evidence: EvidenceItem[];
};

export type ImplementationPackage = {
  suggested_title?: string;
  suggested_meta_description?: string;
  h1?: string;
  suggested_h2_sections?: string[];
  faq_questions?: string[];
  schema_suggestions?: string[];
  internal_links?: string[];
  content_outline?: string[];
  suggested_copy?: string;
  urls_affected?: string[];
  developer_instructions?: string;
  content_writer_instructions?: string;
};

export type GeneratedPageChange = { field: string; current: string | null; proposed: string; reason: string };
export type OnDemandImplementationOutput = {
  summary: string;
  changes: GeneratedPageChange[];
  title: string | null;
  meta_description: string | null;
  h1: string | null;
  h2_sections: string[];
  faq: string[];
  internal_links: string[];
  draft: string | null;
  developer_instructions: string[];
  content_instructions: string[];
  assumptions_requiring_confirmation: string[];
};
export type GenerateImplementationResponse = {
  mode: "rebuild" | "article";
  status: "completed";
  output: OnDemandImplementationOutput;
  ai_execution_id: string;
  cost_usd: number | null;
};
export type OnDemandJob = {
  research_run_id: string;
  kind: "market_exploration" | "winning_page_analysis" | "implementation_generation";
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  error?: string | null;
  result?: GenerateImplementationResponse | null;
};

export type TopCategoryItem = { id: string; name: string; product_count: number };

export type ProductSampleItem = {
  id: string;
  name: string;
  url: string;
  category_name: string | null;
  price: number | null;
  currency: string | null;
  image_url: string | null;
  detail_available: boolean;
};

export type ProductCategoryPreviewItem = {
  name: string;
  image_url: string | null;
  url: string | null;
  product_count: number | null;
  confidence: number | null;
  source: "catalog" | "observed_products" | "classification";
};

export type BusinessInfoItem = { kind: string; label: string; url: string };

export type BrandItem = {
  name: string;
  aliases: string[];
  // True when this name was inferred from the domain rather than found in
  // structured page data — never present a guess as a confirmed fact.
  is_guessed: boolean;
};

export type SuggestedCompetitorItem = {
  id: string;
  domain: string;
  name: string;
  confirmation_status: "pending_user_confirmation" | "auto_confirmed" | "user_confirmed" | "user_rejected";
  classification_confidence: number | null;
  discovery_reason: string | null;
};

// Legacy stages (pre-identity-decoupling runs): pending/partial/ready/
// low_confidence/failed. New stages (once identity resolution has run):
// resolving_identity/provisional/catalog_scanning/ready/needs_confirmation/
// catalog_blocked/failed — see backend StoreUnderstandingResponse's
// docstring for the exact meaning of each.
export type UnderstandingStage =
  | "pending"
  | "partial"
  | "ready"
  | "low_confidence"
  | "failed"
  | "resolving_identity"
  | "provisional"
  | "catalog_scanning"
  | "needs_confirmation"
  | "catalog_blocked";

export type StoreUnderstanding = {
  understanding_stage: UnderstandingStage;
  display_name: string | null;
  description: string | null;
  url: string;
  business_type: string | null;
  country: string | null;
  city: string | null;
  primary_categories: string[];
  target_audience: string[];
  classification_confidence: number | null;
  classification_skipped: boolean;
  identity_source: "web_search" | "crawl" | null;
  identity_confidence: number | null;
  catalog_status: "pending" | "scanning" | "ready" | "partial" | "blocked" | "failed";
  catalog_products_found: number;
  competitor_discovery_status: "pending" | "running" | "ready" | "failed";
  suggested_competitors: SuggestedCompetitorItem[];
  pages_crawled: number;
  products_found: number;
  categories_found: number;
  brands_found: number;
  top_categories: TopCategoryItem[];
  product_samples: ProductSampleItem[];
  category_previews: ProductCategoryPreviewItem[];
  product_count_status: "confirmed" | "estimated" | "unavailable";
  estimated_products_count: number | null;
  sold_brands: string[];
  business_info: BusinessInfoItem[];
  audience_basis: string | null;
  brand: BrandItem | null;
  last_analyzed_at: string | null;
};

export type StoreFeedbackResponse = {
  id: string;
  feedback_type: string;
  issues: string[];
  note: string | null;
  created_at: string;
};

export type ProductDetail = {
  id: string;
  name: string;
  url: string;
  category_name: string | null;
  price: number | null;
  currency: string | null;
  availability: string | null;
  image_url: string | null;
  observed_at: string | null;
  current: Record<string, unknown>;
  checks: ProductPageCheck[];
  image_insights: ProductImageInsight[];
  completion_score: number;
  recommendations: ProductWorkspaceRecommendation[];
};

export type ProductImageInsight = {
  url: string;
  alt: string | null;
  width: number | null;
  height: number | null;
  issues: Array<"missing_alt" | "dimensions_unknown" | "small_dimensions" | "large_dimensions_review" | "duplicate_source">;
  status: "ready" | "review";
};

export type OptimizedImageResult = {
  original_bytes: number;
  optimized_bytes: number;
  saved_percent: number;
  width: number;
  height: number;
  download_url: string;
};

export type ProductPageCheck = {
  key: string;
  label: string;
  status: "present" | "missing";
  current_value: string | null;
  message: string;
};

export type ProductWorkspaceRecommendation = {
  id: string;
  title: string;
  status: string;
  link_basis: "product_id" | "canonical_url";
  implementation: Record<string, unknown>;
};

export type ProductWorkspaceListItem = Omit<ProductDetail, "current" | "checks" | "image_insights" | "recommendations"> & {
  issues_count: number;
};

export type CategoryWorkspaceItem = {
  id: string;
  page_id: string | null;
  name: string;
  url: string | null;
  product_count: number;
  representative_image_url: string | null;
  confidence: number;
  observed_at: string | null;
};

export type PageWorkspaceItem = {
  id: string;
  url: string;
  page_type: "home" | "category" | "product" | "content" | "other";
  title: string | null;
  h1: string | null;
  image_url: string | null;
  completion_score: number;
  issues_count: number;
  observed_at: string | null;
};

export type PageWorkspaceDetail = PageWorkspaceItem & {
  current: Record<string, unknown>;
  checks: ProductPageCheck[];
  recommendations: Array<ProductWorkspaceRecommendation & {link_basis:"page_id"|"canonical_url"}>;
};

export type AlertItem = {
  id: string;
  alert_type: string;
  severity: string;
  title: string;
  message: string;
  status: string;
  related_recommendation_id: string | null;
  related_competitor_id: string | null;
  created_at: string;
};

export type MarketExplorationEstimate = {
  max_queries: number;
  estimated_serp_cost_usd: number;
  includes: string[];
};
export type MarketExplorationResultItem = {
  query: string;
  rank: number;
  domain: string;
  url: string;
  title: string | null;
  entity_type: string;
};
export type MarketExplorationResponse = {
  research_run_id: string;
  status: string;
  topic: string;
  queries: string[];
  results: MarketExplorationResultItem[];
  client_ranks: Record<string, number | null>;
  recurring_domains: Array<{ domain: string; appearances: number }>;
  actual_serp_cost_usd: number;
  warnings: string[];
};
export type WinningPageChange = { area: string; competitor_observation: string; store_observation: string | null; recommended_change: string; evidence_basis: string };
export type WinningPageAnalysisResponse = {
  research_run_id: string;
  status: string;
  query: string;
  competitor_url: string;
  target_url: string | null;
  competitor_facts: Record<string, unknown>;
  target_facts: Record<string, unknown> | null;
  output: {
    summary: string;
    why_this_page_wins: string[];
    gaps: string[];
    changes: WinningPageChange[];
    content_sections: string[];
    assumptions_requiring_confirmation: string[];
  };
  ai_execution_id: string;
  ai_cost_usd: number | null;
};
export type ConvertWinningPageAnalysisResponse = {
  opportunity_id: string;
  recommendation_id: string;
  recommendation_title: string;
};
export type OnDemandAnalysisHistoryItem = {
  research_run_id: string;
  kind: "market_exploration" | "winning_page_analysis";
  status: string;
  topic: string;
  summary: string | null;
  created_at: string;
  completed_at: string | null;
  serp_cost_usd: number;
  ai_cost_usd: number;
  recommendation_id: string | null;
  recommendation_title: string | null;
};

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body.detail ?? `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }
  return response.json();
}

async function postJson<T>(path: string, body?: unknown, extraHeaders?: Record<string, string>): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...extraHeaders },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }
  return response.json();
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }
  return response.json();
}

export async function createStore(url: string): Promise<CreateStoreResponse> {
  return postJson<CreateStoreResponse>("/stores", { url });
}

export async function triggerResearchRun(storeId: string): Promise<CreateStoreResponse> {
  return postJson<CreateStoreResponse>(`/stores/${storeId}/research-runs`);
}

export async function getStore(storeId: string): Promise<StoreDetail> {
  return getJson<StoreDetail>(`/stores/${storeId}`);
}

export async function getIntents(storeId: string): Promise<{ intents: IntentListItem[] }> {
  return getJson(`/stores/${storeId}/intents`);
}

export async function getAIVisibility(storeId: string): Promise<AIVisibilityListResponse> {
  return getJson(`/stores/${storeId}/ai-visibility`);
}

export async function getCrossSurfaceVisibility(storeId: string): Promise<CrossSurfaceVisibilityResponse> {
  return getJson(`/stores/${storeId}/cross-surface-visibility`);
}

export type VisibilitySourceItem = { url: string; title: string; source_type: string };
export type VisibilityCompetitorMentionItem = { name: string; rank: number | null };
export type VisibilityAnswerItem = {
  engine: string;
  status: string;
  raw_answer: string | null;
  brand_mentioned: boolean | null;
  mention_type: string | null;
  mention_rank: number | null;
  recommendation_rank: number | null;
  evidence_quote: string | null;
  competitors_mentioned: VisibilityCompetitorMentionItem[];
  sources: VisibilitySourceItem[];
};
export type VisibilityQuestionItem = {
  question_id: string;
  text: string;
  category: string;
  answers: VisibilityAnswerItem[];
};
export type VisibilityMetricsSummary = {
  successful_answers: number;
  mention_rate: number | null;
  recommendation_rate: number | null;
  avg_recommendation_rank: number | null;
  top_3_rate: number | null;
  share_of_voice: number | null;
  citation_rate: number | null;
  top_competitor: string | null;
  top_competitor_mentions: number;
  week_over_week: {
    previous_run_id: string;
    mention_rate_delta: number | null;
    recommendation_rate_delta: number | null;
    share_of_voice_delta: number | null;
    top_3_rate_delta: number | null;
  } | null;
};
export type VisibilityTopCompetitorItem = {
  name: string;
  domain: string | null;
  appearances: number;
  appearance_rate: number;
  avg_rank: number | null;
  ahead_of_client: boolean;
};
export type VisibilityOpportunityItem = {
  title: string;
  reason: string;
  evidence: string;
  actions: string[];
};
export type VisibilityCitationItem = {
  domain: string;
  citation_count: number;
  supports: "client" | "competitor" | "mixed";
};
// SIGNUP re-scope — one merged, engine-agnostic report block. Never split
// by chatgpt/google in anything that reads this — `engine` only lives on
// the underlying questions[]/sources[] for internal use.
export type VisibilitySignupReport = {
  total_searches: number;
  mentioned_count: number;
  appearance_rate: number | null;
  avg_rank: number | null;
  top3_count: number;
  competitors_ahead_count: number;
  client_rank: number | null;
  competitors_considered_count: number;
  top_competitors: VisibilityTopCompetitorItem[];
  citations: VisibilityCitationItem[];
  opportunities: VisibilityOpportunityItem[];
};
export type VisibilityRunDetail = {
  run_id: string | null;
  status: "no_run_yet" | "running" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  engines_attempted: string[];
  summary: VisibilityMetricsSummary | null;
  questions: VisibilityQuestionItem[];
  competitors: { name: string; mentions: number }[];
  sources: { url: string; title: string; source_type: string; count: number }[];
  report: VisibilitySignupReport | null;
  // Live-progress fields, populated while status === "running" — the
  // unified "تحليل ظهور علامتك" screen polls these for its X/90 counter.
  completed_count: number | null;
  total_planned: number | null;
};

export async function getLatestVisibilityRun(storeId: string): Promise<VisibilityRunDetail> {
  return getJson(`/stores/${storeId}/visibility-runs/latest`);
}

// status is "running" once a real run started, or "not_ready" when no
// visibility questions exist for the store yet (question generation is a
// later step in the same baseline research run, after identity resolves —
// see startVisibilityAnalysisInBackground's retry loop in /signup).
export async function triggerVisibilityRun(storeId: string): Promise<{ visibility_run_id: string | null; status: string }> {
  return postJson(`/stores/${storeId}/visibility-runs`);
}

export type BrandNameConfirmResponse = { name: string; aliases: string[] };

export async function confirmStoreBrandName(storeId: string, name: string): Promise<BrandNameConfirmResponse> {
  return postJson(`/stores/${storeId}/brand-name`, { name });
}

export async function getCostSummary(storeId: string): Promise<CostSummaryResponse> {
  return getJson(`/stores/${storeId}/cost-summary`);
}

export async function getCompetitors(storeId: string): Promise<{ competitors: CompetitorListItem[] }> {
  return getJson(`/stores/${storeId}/competitors`);
}

export async function getOnboardingSummary(storeId: string): Promise<OnboardingSummary> {
  return getJson(`/stores/${storeId}/onboarding-summary`);
}

export async function createOnboardingLead(
  storeId: string,
  name: string,
  contact: string,
): Promise<OnboardingLeadResponse> {
  return postJson<OnboardingLeadResponse>(`/stores/${storeId}/onboarding-lead`, { name, contact });
}

export async function getPageGaps(storeId: string): Promise<{ page_gaps: PageGapItem[] }> {
  return getJson(`/stores/${storeId}/page-gaps`);
}

export async function getResearchTasks(storeId: string): Promise<{ tasks: ResearchTaskItem[] }> {
  return getJson(`/stores/${storeId}/research-tasks`);
}

export async function getFindings(storeId: string): Promise<{ findings: FindingItem[] }> {
  return getJson(`/stores/${storeId}/findings`);
}

export async function getOpportunities(storeId: string): Promise<{ opportunities: OpportunityItem[] }> {
  return getJson(`/stores/${storeId}/opportunities`);
}

export async function getRecommendations(storeId: string): Promise<{ recommendations: RecommendationItem[] }> {
  return getJson(`/stores/${storeId}/recommendations`);
}

export async function getRecommendation(recommendationId: string): Promise<RecommendationDetail> {
  return getJson(`/recommendations/${recommendationId}`);
}

export async function patchRecommendationStatus(
  recommendationId: string,
  status: string,
  implementationUrl?: string
): Promise<RecommendationDetail> {
  return patchJson(`/recommendations/${recommendationId}/status`, {
    status,
    implementation_url: implementationUrl,
  });
}

export async function getRecommendationEvidence(recommendationId: string): Promise<RecommendationEvidenceResponse> {
  return getJson(`/recommendations/${recommendationId}/evidence`);
}

export async function getImplementationPackage(
  recommendationId: string
): Promise<{ implementation_package: ImplementationPackage }> {
  return getJson(`/recommendations/${recommendationId}/implementation-package`);
}

export async function saveImplementationDraft(
  recommendationId: string,
  fields: Record<string, unknown>,
): Promise<{ implementation_package: ImplementationPackage }> {
  return patchJson(`/recommendations/${recommendationId}/implementation-draft`, { fields });
}

export async function generateImplementation(
  recommendationId: string,
  mode: "rebuild" | "article",
): Promise<OnDemandJob> {
  return postJson(`/recommendations/${recommendationId}/generate-implementation`, { mode });
}

export async function getStoreUnderstanding(storeId: string): Promise<StoreUnderstanding> {
  return getJson(`/stores/${storeId}/understanding`);
}

export async function postCompetitorConfirmation(
  storeId: string,
  competitorId: string,
  action: "confirm" | "reject"
): Promise<SuggestedCompetitorItem> {
  return postJson(`/stores/${storeId}/competitors/${competitorId}/confirmation`, { action });
}

export async function postStoreFeedback(
  storeId: string,
  feedbackType: "confirmed" | "incorrect",
  issues: string[] = [],
  note?: string
): Promise<StoreFeedbackResponse> {
  return postJson(`/stores/${storeId}/understanding/feedback`, { feedback_type: feedbackType, issues, note });
}

export async function getProductDetail(storeId: string, productId: string): Promise<ProductDetail> {
  return getJson(`/stores/${storeId}/products/${productId}`);
}

export async function optimizeProductImage(storeId:string,productId:string,imageUrl:string):Promise<OptimizedImageResult>{
  return postJson(`/stores/${storeId}/products/${productId}/optimize-image`,{image_url:imageUrl,quality:82});
}

export async function getProducts(storeId: string): Promise<{ products: ProductWorkspaceListItem[] }> {
  return getJson(`/stores/${storeId}/products`);
}

export async function getCategories(storeId: string): Promise<{ categories: CategoryWorkspaceItem[] }> {
  return getJson(`/stores/${storeId}/categories`);
}

export async function getPages(storeId: string): Promise<{ pages: PageWorkspaceItem[] }> {
  return getJson(`/stores/${storeId}/pages`);
}

export async function getPageDetail(storeId: string, pageId: string): Promise<PageWorkspaceDetail> {
  return getJson(`/stores/${storeId}/pages/${pageId}`);
}

export type PageScreenshotResult={screenshot_url:string;mobile:boolean;width:number;height:number;annotations:Array<{key:string;x:number;y:number;width:number;height:number}>};
export async function capturePageScreenshot(storeId:string,pageId:string,mobile=false):Promise<PageScreenshotResult>{
  return postJson(`/stores/${storeId}/pages/${pageId}/screenshot`,{mobile});
}

export async function getAlerts(storeId: string): Promise<{ alerts: AlertItem[] }> {
  return getJson(`/stores/${storeId}/alerts`);
}

export async function patchAlertStatus(alertId: string, status: string): Promise<AlertItem> {
  return patchJson(`/alerts/${alertId}/status`, { status });
}

export async function getMarketExplorationEstimate(storeId: string): Promise<MarketExplorationEstimate> {
  return getJson(`/stores/${storeId}/market-explorations/estimate`);
}

export async function runMarketExploration(storeId: string, topic: string): Promise<OnDemandJob> {
  return postJson(`/stores/${storeId}/market-explorations`, { topic, max_queries: 3 });
}

export async function analyzeWinningPage(
  storeId: string,
  payload: { market_research_run_id: string; query: string; competitor_url: string; target_url?: string },
): Promise<OnDemandJob> {
  return postJson(`/stores/${storeId}/winning-page-analyses`, payload);
}

export async function convertWinningPageAnalysis(
  storeId: string,
  analysisRunId: string,
): Promise<ConvertWinningPageAnalysisResponse> {
  return postJson(`/stores/${storeId}/winning-page-analyses/${analysisRunId}/convert`);
}

export async function getOnDemandAnalysisHistory(storeId: string): Promise<{ analyses: OnDemandAnalysisHistoryItem[] }> {
  return getJson(`/stores/${storeId}/on-demand-analyses`);
}

export async function getMarketExploration(storeId: string, runId: string): Promise<MarketExplorationResponse> {
  return getJson(`/stores/${storeId}/market-explorations/${runId}`);
}

export async function getWinningPageAnalysis(storeId: string, runId: string): Promise<WinningPageAnalysisResponse> {
  return getJson(`/stores/${storeId}/winning-page-analyses/${runId}`);
}

export async function getOnDemandJobStatus(storeId: string, runId: string): Promise<OnDemandJob> {
  return getJson(`/stores/${storeId}/on-demand-analyses/${runId}/status`);
}

export async function retryOnDemandJob(storeId: string, runId: string): Promise<OnDemandJob> {
  return postJson(`/stores/${storeId}/on-demand-analyses/${runId}/retry`);
}

export async function waitForOnDemandJob(storeId: string, runId: string): Promise<OnDemandJob> {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const job = await getOnDemandJobStatus(storeId, runId);
    if (job.status === "completed") return job;
    if (job.status === "failed" || job.status === "cancelled") throw new Error(job.error ?? "تعذر إكمال المهمة");
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error("ما زالت المهمة تعمل. يمكنك العودة لاحقًا وستجدها محفوظة في السجل.");
}

// ---------------------------------------------------------------------------
// PreviewReport (MVP) — deliberately isolated from every type/function above:
// no store_id, no ResearchRun. One create call, one poll loop, one fetch of
// the finished report — every screen after that reads from the same object,
// never a new request. See backend/app/models/preview_report.py.

export type PreviewQuerySourceResult = {
  status: "success" | "failed";
  brand_found: boolean | null;
  position: number | null;
  results?: Array<{ rank: number; domain: string; url: string; title: string | null }>;
  raw_result?: string;
  sources?: Array<{ url: string }>;
};

export type PreviewQueryResult = {
  query: string;
  subject: string | null;
  subject_type: "category" | "product" | null;
  google: PreviewQuerySourceResult;
  ai: PreviewQuerySourceResult;
};

export type PreviewCompetitor = {
  domain: string;
  appearances: number;
  average_rank: number | null;
  visibility_percentage: number | null;
  queries: string[];
};

// measured: enough successful search checks to trust an exact percentage.
// estimated: too thin a sample to trust an exact number — can flag a
// confirmed weakness (level "low" + display_range "under_50") but can
// never certify strong visibility from a thin sample (level "limited").
export type PreviewVisibilityMeasured = {
  mode: "measured";
  score: number | null;
  brand_mentions: number;
  successful_checks: number;
  google_score: number | null;
  ai_score: number | null;
};

export type PreviewVisibilityEstimated = {
  mode: "estimated";
  score: null;
  level: "low" | "limited";
  display_range?: "under_50";
  reasons?: string[];
};

export type PreviewVisibility = PreviewVisibilityMeasured | PreviewVisibilityEstimated;

export type PreviewRecommendation = {
  title: string;
  reason: string;
  action: string;
  topic: string | null;
  evidence: string[];
};

export type PreviewReportData = {
  id: string;
  status: string;
  store: {
    url: string;
    domain: string;
    logo: string | null;
    brand_name: string;
    category: string;
    categories: string[];
    products: string[];
  };
  visibility: PreviewVisibility;
  competitors: PreviewCompetitor[];
  queries: PreviewQueryResult[];
  recommendation: PreviewRecommendation;
  generated_at: string;
};

export type PreviewReportStatusResponse = {
  id: string;
  status: "processing" | "ready" | "failed";
  report: PreviewReportData | null;
  error_message: string | null;
};

export async function createPreviewReport(
  storeUrl: string,
  bypassToken?: string | null
): Promise<{ report_id: string; status: string }> {
  return postJson(
    "/preview-reports",
    { store_url: storeUrl },
    bypassToken ? { "X-Preview-Bypass": bypassToken } : undefined
  );
}

export async function getPreviewReport(reportId: string): Promise<PreviewReportStatusResponse> {
  return getJson(`/preview-reports/${reportId}`);
}

export type PreviewJoinBetaRequest = {
  name: string;
  email: string;
  report_feedback: string;
  interest_level: string;
};

export async function joinPreviewReportBeta(
  reportId: string,
  payload: PreviewJoinBetaRequest
): Promise<{ id: string }> {
  return postJson(`/preview-reports/${reportId}/join`, payload);
}
