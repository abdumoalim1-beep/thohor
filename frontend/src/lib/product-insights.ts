import type { IntentListItem, StoreUnderstanding } from "./api";

export const COMMERCIAL_STAGE_LABELS: Record<string, string> = {
  awareness: "استكشاف وفهم",
  consideration: "مقارنة وتقييم",
  purchase: "قريبة من الشراء",
};

export const DEMAND_LABELS: Record<string, string> = {
  low: "طلب تقديري منخفض",
  medium: "طلب تقديري متوسط",
  high: "طلب تقديري مرتفع",
};

export function commercialStageLabel(stage: string | null): string {
  return stage ? (COMMERCIAL_STAGE_LABELS[stage] ?? "مرحلة غير مؤكدة") : "مرحلة غير مؤكدة";
}

export function estimatedDemandLabel(demand: string | null): string {
  return demand ? (DEMAND_LABELS[demand] ?? "الطلب التقديري غير مؤكد") : "الطلب التقديري غير مؤكد";
}

export type IntentSummary = {
  topics: number;
  purchase: number;
  highEstimatedDemand: number;
  visibleInTop10: number;
  byStage: Record<"awareness" | "consideration" | "purchase" | "unknown", number>;
};

export function summarizeIntents(intents: IntentListItem[]): IntentSummary {
  const uniqueTopics = new Set(intents.map((intent) => intent.topic.trim()).filter(Boolean));
  const byStage: IntentSummary["byStage"] = { awareness: 0, consideration: 0, purchase: 0, unknown: 0 };

  for (const intent of intents) {
    if (intent.commercial_stage === "awareness" || intent.commercial_stage === "consideration" || intent.commercial_stage === "purchase") {
      byStage[intent.commercial_stage] += 1;
    } else {
      byStage.unknown += 1;
    }
  }

  return {
    topics: uniqueTopics.size,
    purchase: byStage.purchase,
    highEstimatedDemand: intents.filter((intent) => intent.estimated_demand === "high").length,
    visibleInTop10: intents.filter((intent) => intent.client_rank !== null && intent.client_rank <= 10).length,
    byStage,
  };
}

export function storeUncertainties(understanding: StoreUnderstanding): string[] {
  const uncertainties: string[] = [];

  if (!understanding.business_type) uncertainties.push("لم نتأكد بعد من وصف النشاط التجاري.");
  if (understanding.primary_categories.length === 0 && understanding.top_categories.length === 0) {
    uncertainties.push("لم نتأكد بعد من التصنيفات الرئيسية للمتجر.");
  }
  if (understanding.products_found === 0 && understanding.product_samples.length === 0) {
    uncertainties.push("لم نستخرج منتجات محددة يمكن تأكيدها بعد.");
  } else if (understanding.products_found === 0) {
    uncertainties.push("رصدنا أسماء وصور منتجات من بيانات صفحات المتجر، لكن لم نتأكد بعد من العدد الكامل أو تفاصيل الكتالوج.");
  }
  if (!understanding.brand || understanding.brand.is_guessed) {
    uncertainties.push("لم نتأكد من الاسم التجاري من بيانات صريحة داخل صفحات المتجر.");
  }
  if (understanding.understanding_stage === "partial") {
    uncertainties.push("التحليل ما زال جزئيًا وقد تتغير النتائج بعد قراءة صفحات إضافية.");
  }

  uncertainties.push("لا توجد بيانات كافية هنا لاستنتاج الجمهور أو حجم الطلب؛ لذلك لا يعرضهما ظهور كحقائق.");
  return uncertainties;
}
