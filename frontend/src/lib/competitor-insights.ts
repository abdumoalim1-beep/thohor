import { CompetitorListItem } from "@/lib/api";

export type CompetitorInsights = {
  strengths: string[];
  weaknesses: string[];
};

/** Deterministic synthesis from real, already-measured fields only — same
 * style as Overview's synthesizeStatus(): no AI, no invented signal. Every
 * sentence traces directly to a field on CompetitorListItem. */
export function synthesizeCompetitorInsights(c: CompetitorListItem): CompetitorInsights {
  const strengths: string[] = [];
  const weaknesses: string[] = [];

  if (c.serp_appearances > 0) {
    strengths.push(`يظهر في ${c.serp_appearances} استعلام بحث على Google`);
  } else {
    weaknesses.push("لا يظهر في نتائج Google لنفس النوايا التي نراقبها");
  }

  if (c.avg_serp_rank !== null && c.avg_serp_rank <= 3) {
    strengths.push(`يحتل مراكز متقدمة (متوسط الترتيب ${c.avg_serp_rank.toFixed(1)})`);
  } else if (c.avg_serp_rank !== null && c.avg_serp_rank > 7) {
    weaknesses.push(`ترتيبه في Google متأخر نسبيًا (متوسط ${c.avg_serp_rank.toFixed(1)})`);
  }

  if (c.ai_citation_count > 0) {
    strengths.push(`يُستشهد به في إجابات AI (${c.ai_citation_count} مرة)`);
  } else {
    weaknesses.push("لا يُستشهد به في إجابات محركات AI");
  }

  if (c.shared_stable_intents_count >= 3) {
    strengths.push(`ينافسك على ${c.shared_stable_intents_count} نية بحث مشتركة`);
  }

  return { strengths: strengths.slice(0, 2), weaknesses: weaknesses.slice(0, 2) };
}
