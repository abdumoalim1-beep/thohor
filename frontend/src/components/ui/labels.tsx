import { Badge, BadgeVariant } from "./Badge";

/** Single source of truth for the 4 measured AI/search surfaces — was
 * previously redefined independently in Overview and Market pages. */
export const SURFACE_LABELS: Record<string, string> = {
  google: "Google",
  chatgpt: "ChatGPT",
  gemini: "Gemini",
  claude: "Claude",
  perplexity: "Perplexity",
};

export function surfaceLabel(surface: string): string {
  return SURFACE_LABELS[surface] ?? surface;
}

/** Single source of truth for the 9 research pipeline steps — previously 2
 * independently-maintained copies (Overview: narrative, Research: technical)
 * with different wording for the same key. Narrative framing throughout:
 * the product did this analysis for you, not "here is a technical log". */
export const AGENT_TYPE_LABELS: Record<string, string> = {
  crawl_agent_run: "نفهم متجرك",
  ai_classification_agent_run: "نصنّف نشاطك التجاري",
  intent_agent_run: "نكتشف كيف يبحث عملاؤك",
  serp_agent_run: "نقيس ظهورك في Google",
  prompt_family_agent_run: "نبني أسئلة طبيعية لعملائك",
  ai_visibility_agent_run: "نقيس ظهورك في محركات AI",
  iterative_research_agent_run: "نحقق في المنافسين والفرص",
  opportunity_recommendation_agent_run: "نبني خطة تحسينك",
  monitoring_and_alerts_agent_run: "نراقب التغيرات",
};

export function agentTypeLabel(type: string): string {
  return AGENT_TYPE_LABELS[type] ?? type;
}

/** Single source of truth for Recommendation.status — previously duplicated
 * verbatim across the list and detail pages. */
export const RECOMMENDATION_STATUS_LABELS: Record<string, string> = {
  new: "جديدة",
  planned: "مخطَّطة",
  in_progress: "قيد التنفيذ",
  implemented: "نُفِّذت",
  monitoring: "قيد المراقبة",
  successful: "ناجحة",
  partial: "تحسّن جزئي",
  no_detectable_impact: "لا تغيّر ملحوظ",
  regressed: "تراجعت",
  dismissed: "مرفوضة",
  superseded: "استُبدلت",
};

const RECOMMENDATION_STATUS_VARIANT: Record<string, BadgeVariant> = {
  new: "primary",
  planned: "info",
  in_progress: "info",
  implemented: "neutral",
  monitoring: "warning",
  successful: "success",
  partial: "warning",
  no_detectable_impact: "neutral",
  regressed: "danger",
  dismissed: "neutral",
  superseded: "neutral",
};

export function RecommendationStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={RECOMMENDATION_STATUS_VARIANT[status] ?? "neutral"}>
      {RECOMMENDATION_STATUS_LABELS[status] ?? status}
    </Badge>
  );
}

/** confidence_tier — deterministic evidence-derived tier from the Beta
 * Readiness Remediation work, now given one canonical visual treatment. */
const CONFIDENCE_LABELS: Record<string, string> = { high: "ثقة عالية", medium: "ثقة متوسطة", low: "ثقة منخفضة" };
const CONFIDENCE_VARIANT: Record<string, BadgeVariant> = { high: "success", medium: "warning", low: "neutral" };

export function ConfidenceBadge({ tier }: { tier: string }) {
  return <Badge variant={CONFIDENCE_VARIANT[tier] ?? "neutral"}>{CONFIDENCE_LABELS[tier] ?? tier}</Badge>;
}

/** Generic High/Medium/Low priority badge — used for opportunity impact and
 * effort, kept distinct from ConfidenceBadge (different meaning) but same
 * visual language. */
const PRIORITY_LABELS: Record<string, string> = { high: "مرتفع", medium: "متوسط", low: "منخفض" };
const PRIORITY_VARIANT: Record<string, BadgeVariant> = { high: "danger", medium: "warning", low: "neutral" };

export function PriorityBadge({ level, label }: { level: "high" | "medium" | "low"; label?: string }) {
  return <Badge variant={PRIORITY_VARIANT[level]}>{label ?? PRIORITY_LABELS[level]}</Badge>;
}

export function effortLabel(effort: string): string {
  if (effort === "low") return "جهد منخفض";
  if (effort === "high") return "جهد كبير";
  return "جهد متوسط";
}

/** Trust-gate feedback issue options — single source for the FeedbackModal
 * checkbox list and any future rendering of submitted feedback. */
export const FEEDBACK_ISSUE_LABELS: Record<string, string> = {
  business_type_wrong: "تخصص المتجر غير صحيح",
  categories_wrong: "بعض التصنيفات غير صحيحة",
  products_wrong: "المنتجات غير صحيحة",
  brand_wrong: "العلامة التجارية غير صحيحة",
  other: "شيء آخر",
};

/** Competitor classification — was independently reimplemented in
 * competitors/market/recommendation-detail pages via classification-labels.ts;
 * this re-exports the same map through the shared labels module so callers
 * only need one import path going forward. */
export { CLASSIFICATION_LABELS, classificationLabel } from "@/lib/competitor-labels";
