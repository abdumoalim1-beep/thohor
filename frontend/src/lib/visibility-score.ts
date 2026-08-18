import type { OnboardingSummary } from "./api.ts";

const AR_DIGITS = ["٠", "١", "٢", "٣", "٤", "٥", "٦", "٧", "٨", "٩"];
export function arDigits(n: number): string {
  return String(n)
    .split("")
    .map((c) => AR_DIGITS[Number(c)] ?? c)
    .join("");
}

// The recommendation engine's what_to_do/what_we_found text is generated
// by the (unchanged, protected) backend — it can legitimately use SEO
// terms like "نية" that this wizard's own copy deliberately avoids. This
// is a display-only mechanical filter over that free-form text, applied
// only in /signup; it never touches the stored recommendation itself.
// Arabic letters aren't \w in JS regex, so \b doesn't work here — a
// lookaround excluding neighbouring Arabic letters is used instead so we
// only replace the whole word, never a substring of a longer one.
const AR_LETTER = "\\u0600-\\u06FF";
const MERCHANT_TEXT_REPLACEMENTS: [string, string][] = [
  ["نوايا", "عمليات بحث"],
  ["النوايا", "عمليات البحث"],
  ["نية", "بحث"],
  ["النية", "البحث"],
  ["الفرصة", "هذا التحسين"],
  ["فرصة", "تحسين"],
  ["التغطية", "نسبة الظهور"],
  ["تغطية", "نسبة ظهور"],
];

export function sanitizeMerchantText(text: string): string {
  let result = text;
  for (const [term, replacement] of MERCHANT_TEXT_REPLACEMENTS) {
    const pattern = new RegExp(`(?<![${AR_LETTER}])${term}(?![${AR_LETTER}])`, "g");
    result = result.replace(pattern, replacement);
  }
  return result;
}

const ORDINALS: Record<number, string> = {
  1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع", 5: "الخامس",
  6: "السادس", 7: "السابع", 8: "الثامن", 9: "التاسع", 10: "العاشر",
};

/** "المركز الثالث" for ranks we have a word for, "المركز رقم ١٤" beyond
 * that, or an explicit not-measured line — never a fabricated rank. */
export function bestRankLabel(rank: number | null): string {
  if (rank === null) return "لم نسجّل ترتيبًا ضمن أول 10 نتائج بعد";
  const ordinal = ORDINALS[rank];
  return ordinal ? `المركز ${ordinal}` : `المركز رقم ${arDigits(rank)}`;
}

// The merchant-facing rewording of commercial_stage — deliberately separate
// from lib/product-insights.ts's commercialStageLabel (استكشاف وفهم/...),
// which other dashboard pages already rely on. Signup speaks to a shop
// owner, not an SEO practitioner: "what is the customer trying to do?"
const STAGE_ACTION: Record<string, string> = {
  awareness: "يبحث عن منتج",
  consideration: "يقارن بين الخيارات",
  purchase: "يختار متجرًا للشراء",
};
const STAGE_NOUN: Record<string, string> = {
  awareness: "البحث عن منتج",
  consideration: "مقارنة الخيارات",
  purchase: "اختيار متجر للشراء",
};

export function stageActionLabel(stage: string | null): string {
  return (stage && STAGE_ACTION[stage]) || "هذا النوع من البحث";
}
export function stageNounLabel(stage: string | null): string {
  return (stage && STAGE_NOUN[stage]) || "هذا النوع من البحث";
}

export type VisibilityLevel = "منخفض" | "متوسط" | "مرتفع";

/** A transparent, documented display heuristic over the real measured
 * appearance rate (store_sample_appearances / sample_size) — not a
 * proprietary score, and never computed when there's no sample to measure. */
export function classifyVisibility(summary: OnboardingSummary): VisibilityLevel | null {
  if (summary.sample_size === 0) return null;
  const ratio = summary.store_sample_appearances / summary.sample_size;
  if (ratio >= 0.6) return "مرتفع";
  if (ratio >= 0.3) return "متوسط";
  return "منخفض";
}

/** The dramatic one-line headline for the result step's reveal — honest
 * thresholds only, and an explicit "not enough data" line instead of
 * forcing a verdict out of a tiny sample. */
export function resultHeadline(summary: OnboardingSummary): string {
  if (summary.sample_size < 3) {
    return "لم تكتمل بيانات كافية للحكم على مستوى ظهور متجرك بعد.";
  }
  const ratio = summary.store_sample_appearances / summary.sample_size;
  if (ratio < 0.5) {
    return "متجرك لا يظهر في أكثر من نصف عمليات البحث المرتبطة بمنتجاتك.";
  }
  if (ratio < 0.8) {
    return `متجرك يظهر في ${arDigits(summary.store_sample_appearances)} من ${arDigits(summary.sample_size)} عمليات بحث مرتبطة بمنتجاتك.`;
  }
  return "متجرك يظهر في أغلب عمليات البحث التي اختبرناها.";
}

/** One honest sentence describing where the store is strongest/weakest
 * across the search stages we actually measured — falls back to a neutral
 * line whenever the data doesn't support a specific comparison (fewer than
 * two measured stages, or a tie), rather than forcing one. */
export function visibilityNarrative(summary: OnboardingSummary): string {
  if (summary.sample_size === 0) {
    return "لم نقِس ظهور متجرك في عمليات بحث كافية بعد.";
  }
  if (summary.store_sample_appearances === 0) {
    return "متجرك لا يظهر بعد في عمليات البحث التي قِسناها.";
  }
  if (summary.store_sample_appearances === summary.sample_size) {
    return "متجرك يظهر في كل عمليات البحث التي قِسناها حتى الآن — نتيجة قوية.";
  }

  const stagesWithData = summary.stage_breakdown.filter((s) => s.measured > 0 && s.stage !== "unknown");
  if (stagesWithData.length < 2) {
    return "لم يظهر تفوق واضح لمتجرك في العينة الحالية.";
  }

  const withRatio = stagesWithData.map((s) => ({ ...s, ratio: s.top10 / s.measured }));
  const best = withRatio.reduce((a, b) => (b.ratio > a.ratio ? b : a));
  const worst = withRatio.reduce((a, b) => (b.ratio < a.ratio ? b : a));

  if (best.stage === worst.stage || best.ratio === worst.ratio) {
    return "لم يظهر تفوق واضح لمتجرك في العينة الحالية.";
  }

  return `متجرك قوي عندما ${stageActionLabel(best.stage)}، لكنه يغيب عندما ${stageActionLabel(worst.stage)}.`;
}

/** The single strongest stage for the result step's stat line — null when
 * there isn't enough signal to name one honestly. */
export function bestStageLabel(summary: OnboardingSummary): string | null {
  const stagesWithData = summary.stage_breakdown.filter((s) => s.measured > 0 && s.stage !== "unknown" && s.top10 > 0);
  if (stagesWithData.length === 0) return null;
  const withRatio = stagesWithData.map((s) => ({ ...s, ratio: s.top10 / s.measured }));
  const best = withRatio.reduce((a, b) => (b.ratio > a.ratio ? b : a));
  return stageNounLabel(best.stage);
}

/** Why the top real competitor tends to win, in one honest line — only
 * when the backend found a clear stage concentration; otherwise a plain
 * fallback rather than an invented reason. */
export function competitorReasonLabel(strongerStage: string | null): string | null {
  if (!strongerStage) return null;
  return `هذا المتجر يظهر أمام العملاء أكثر من متجرك عندما ${stageActionLabel(strongerStage)}.`;
}

export type CompetitorGapExample = { topic: string; competitorName: string };

/** One real search where a tracked competitor showed up and the store
 * didn't — for the market step's single concrete example. Null when the
 * sample doesn't contain one, never invented. */
export function competitorGapExample(summary: OnboardingSummary): CompetitorGapExample | null {
  const hit = summary.sample_intents.find(
    (s) => (s.client_rank === null || s.client_rank > 10) && s.top_competitor_domain,
  );
  if (!hit) return null;
  return { topic: hit.topic, competitorName: hit.top_competitor_name ?? hit.top_competitor_domain ?? "" };
}

/** A share of the measured sample as a whole percent — null (never 0 or a
 * fabricated figure) when there was no sample to divide by. */
export function competitorSharePercent(count: number, total: number): number | null {
  if (total <= 0) return null;
  return Math.round((count / total) * 100);
}

export type RevealBadge = "seen" | "not_seen" | "competitor";

/** The تظهر / لا تظهر / يظهر منافس بدلاً منك badge for one real sample
 * search — used by both the result step's reveal sequence and the market
 * step's search list. */
export function revealBadge(clientRank: number | null, competitorDomain: string | null): RevealBadge {
  if (clientRank !== null && clientRank <= 10) return "seen";
  if (competitorDomain) return "competitor";
  return "not_seen";
}

export function revealBadgeLabel(badge: RevealBadge, competitorName?: string | null): string {
  if (badge === "seen") return "ظهر متجرك";
  if (badge === "competitor") return `ظهر ${competitorName ?? "منافسك"} بدلًا منك`;
  return "لم يظهر متجرك";
}
