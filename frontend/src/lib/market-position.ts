import type { CompetitorListItem, IntentListItem, StoreUnderstanding } from "./api";

export type MarketEntity = {
  id: string;
  x: number;
  y: number;
  kind: "store" | "direct" | "marketplace" | "source";
  label: string;
};

function clamp(value: number): number {
  return Math.max(6, Math.min(94, Math.round(value)));
}

export function marketEntityKind(competitor: CompetitorListItem): MarketEntity["kind"] {
  if (competitor.is_business_competitor) return "direct";
  if (competitor.classification === "marketplace" || competitor.competitor_type === "marketplace") return "marketplace";
  return "source";
}

export function buildMarketMap(competitors: CompetitorListItem[], intents: IntentListItem[]): MarketEntity[] {
  const maxBreadth = Math.max(1, intents.length, ...competitors.map((item) => item.shared_stable_intents_count));
  const maxPresence = Math.max(1, ...competitors.map((item) => item.serp_appearances + item.ai_citation_count));
  const visibleIntents = intents.filter((intent) => intent.client_rank !== null && intent.client_rank <= 10).length;

  const entities: MarketEntity[] = competitors.map((item) => ({
    id: item.id,
    x: clamp((item.shared_stable_intents_count / maxBreadth) * 100),
    y: clamp(((item.serp_appearances + item.ai_citation_count) / maxPresence) * 100),
    kind: marketEntityKind(item),
    label: item.domain,
  }));

  entities.push({
    id: "store",
    x: clamp((intents.length / maxBreadth) * 100),
    y: clamp(intents.length > 0 ? (visibleIntents / intents.length) * 100 : 0),
    kind: "store",
    label: "متجرك",
  });
  return entities;
}

export function storeIdentitySignals(understanding: StoreUnderstanding): string[] {
  const signals: string[] = [];
  const categories = understanding.primary_categories.length > 0
    ? understanding.primary_categories
    : understanding.top_categories.map((category) => category.name);

  if (understanding.business_type) signals.push(`النشاط المرصود: ${understanding.business_type}`);
  if (categories.length === 1) signals.push(`متجر متخصص بوضوح في ${categories[0]}`);
  if (categories.length > 1 && categories.length <= 4) signals.push(`متجر متخصص يغطي ${categories.length} فئات مترابطة`);
  if (categories.length > 4) signals.push(`كتالوج واسع يغطي ${categories.length} فئات مكتشفة`);
  if (understanding.brands_found > 1) signals.push(`يبيع عدة علامات تجارية (${understanding.brands_found} مرصودة)`);
  if (understanding.products_found > 0) signals.push(`الهوية مبنية على ${understanding.products_found} منتجًا مكتشفًا، لا على وصف عام فقط`);
  return signals;
}
