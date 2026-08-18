import type { IntentListItem } from "./api";

export type VisibilityState = "top3" | "top10" | "top20" | "not_seen" | "failed" | "insufficient";

export function visibilityState(intent: IntentListItem): VisibilityState {
  if (intent.client_rank !== null && intent.client_rank <= 3) return "top3";
  if (intent.client_rank !== null && intent.client_rank <= 10) return "top10";
  if (intent.client_rank !== null && intent.client_rank <= 20) return "top20";
  if (intent.search_status === "failed") return "failed";
  if (intent.search_status === "measured" || intent.client_rank !== null || intent.client_url) return "not_seen";
  return "insufficient";
}

export const VISIBILITY_LABELS: Record<VisibilityState, string> = {
  top3: "يتصدر",
  top10: "يظهر",
  top20: "قريب من الظهور",
  not_seen: "لم نرصد ظهوره",
  failed: "تعذر الفحص",
  insufficient: "بيانات غير كافية",
};

export function groupSimilarSearches(intents: IntentListItem[]): IntentListItem[] {
  const best = new Map<string, IntentListItem>();
  for (const intent of intents) {
    const key = intent.topic.trim().replace(/\s+/g, " ").toLocaleLowerCase("ar");
    const current = best.get(key);
    if (!current || evidenceValue(intent) < evidenceValue(current)) best.set(key, intent);
  }
  return [...best.values()];
}

function evidenceValue(intent: IntentListItem): number {
  if (intent.client_rank !== null) return intent.client_rank;
  if (intent.search_status === "measured") return 100;
  if (intent.search_status === "failed") return 200;
  return 300;
}

const NON_COMMERCIAL_CATEGORIES = ["الشروط", "الاستبدال", "الاسترجاع", "التوصيل", "الدفع", "سياسة", "الأحكام"];
const GENERIC_TOPICS = new Set(["تسوق", "متجر", "شراء"]);
export function isUsefulProductSearch(intent: IntentListItem): boolean {
  const category = (intent.category ?? "").toLocaleLowerCase("ar");
  if (NON_COMMERCIAL_CATEGORIES.some((word) => category.includes(word))) return false;
  return !GENERIC_TOPICS.has(intent.topic.trim().toLocaleLowerCase("ar"));
}

export function rankValue(intent: IntentListItem): number {
  return intent.client_rank ?? 999;
}

export function visibilityCounts(intents: IntentListItem[]) {
  const counts: Record<VisibilityState, number> = { top3: 0, top10: 0, top20: 0, not_seen: 0, failed: 0, insufficient: 0 };
  intents.forEach((intent) => { counts[visibilityState(intent)] += 1; });
  return counts;
}
