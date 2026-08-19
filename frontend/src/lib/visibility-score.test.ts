import assert from "node:assert/strict";
import test from "node:test";

import type { OnboardingSummary } from "./api.ts";
import {
  bestRankLabel,
  bestStageLabel,
  classifyVisibility,
  competitorGapExample,
  competitorReasonLabel,
  competitorSharePercent,
  resultHeadline,
  revealBadge,
  revealBadgeLabel,
  sanitizeMerchantText,
  visibilityNarrative,
} from "./visibility-score.ts";

function summary(overrides: Partial<OnboardingSummary> = {}): OnboardingSummary {
  return {
    measured_count: 6,
    sample_size: 6,
    store_sample_appearances: 3,
    best_rank: 1,
    stage_breakdown: [],
    top_competitors: [],
    sample_intents: [],
    products_found: 10,
    categories_found: 2,
    ai_measured_count: 0,
    ai_sample_size: 0,
    ai_store_sample_appearances: 0,
    ...overrides,
  };
}

test("classifyVisibility returns null instead of a fake label when nothing was measured", () => {
  assert.equal(classifyVisibility(summary({ sample_size: 0, store_sample_appearances: 0 })), null);
});

test("classifyVisibility uses merchant-facing levels, not jargon grades", () => {
  assert.equal(classifyVisibility(summary({ sample_size: 10, store_sample_appearances: 7 })), "مرتفع");
  assert.equal(classifyVisibility(summary({ sample_size: 10, store_sample_appearances: 4 })), "متوسط");
  assert.equal(classifyVisibility(summary({ sample_size: 10, store_sample_appearances: 2 })), "منخفض");
});

test("resultHeadline refuses to render a verdict from too small a sample", () => {
  const line = resultHeadline(summary({ sample_size: 2, store_sample_appearances: 1 }));
  assert.match(line, /لم تكتمل بيانات كافية/);
});

test("resultHeadline calls out majority-missing visibility honestly", () => {
  const line = resultHeadline(summary({ sample_size: 10, store_sample_appearances: 3 }));
  assert.match(line, /لا يظهر في أكثر من نصف/);
});

test("resultHeadline reports the real fraction in the middle band", () => {
  const line = resultHeadline(summary({ sample_size: 7, store_sample_appearances: 5 }));
  assert.match(line, /5 من 7/);
});

test("resultHeadline uses a qualitative line once visibility is strong, not a fabricated near-100 number", () => {
  const line = resultHeadline(summary({ sample_size: 10, store_sample_appearances: 9 }));
  assert.match(line, /أغلب عمليات البحث/);
});

test("visibilityNarrative never invents a stage comparison when fewer than two stages have data", () => {
  const line = visibilityNarrative(
    summary({
      store_sample_appearances: 2,
      stage_breakdown: [{ stage: "consideration", measured: 6, top10: 2 }],
    }),
  );
  assert.doesNotMatch(line, /لكنه يغيب/);
  assert.match(line, /لم يظهر تفوق واضح/);
});

test("visibilityNarrative reports a real best/worst stage split in merchant language, never the SEO jargon labels", () => {
  const line = visibilityNarrative(
    summary({
      store_sample_appearances: 3,
      stage_breakdown: [
        { stage: "awareness", measured: 4, top10: 4 },
        { stage: "purchase", measured: 4, top10: 0 },
      ],
    }),
  );
  assert.match(line, /يبحث عن منتج/);
  assert.match(line, /يختار متجرًا للشراء/);
  assert.doesNotMatch(line, /استكشاف|نية|تصنيف/);
});

test("visibilityNarrative falls back to a neutral line on a tie instead of picking a fake winner", () => {
  const line = visibilityNarrative(
    summary({
      store_sample_appearances: 4,
      stage_breakdown: [
        { stage: "awareness", measured: 4, top10: 2 },
        { stage: "consideration", measured: 4, top10: 2 },
      ],
    }),
  );
  assert.match(line, /لم يظهر تفوق واضح/);
});

test("bestStageLabel stays null when nothing clears the bar, never guesses", () => {
  assert.equal(bestStageLabel(summary({ stage_breakdown: [] })), null);
  assert.equal(
    bestStageLabel(summary({ stage_breakdown: [{ stage: "awareness", measured: 4, top10: 0 }] })),
    null,
  );
});

test("bestStageLabel names the real strongest stage in merchant language", () => {
  const label = bestStageLabel(
    summary({ stage_breakdown: [{ stage: "purchase", measured: 4, top10: 3 }, { stage: "awareness", measured: 4, top10: 1 }] }),
  );
  assert.equal(label, "اختيار متجر للشراء");
});

test("bestRankLabel never fabricates a rank when none was observed", () => {
  assert.match(bestRankLabel(null), /لم نسجّل/);
});

test("bestRankLabel uses Arabic ordinals for ranks we have words for, and a numbered fallback beyond that", () => {
  assert.equal(bestRankLabel(1), "المركز الأول");
  assert.equal(bestRankLabel(3), "المركز الثالث");
  assert.equal(bestRankLabel(14), "المركز رقم 14");
});

test("competitorReasonLabel stays silent instead of guessing when the backend found no clear stage concentration", () => {
  assert.equal(competitorReasonLabel(null), null);
  assert.match(competitorReasonLabel("purchase") ?? "", /يختار متجرًا للشراء/);
});

test("competitorGapExample returns null instead of inventing an example when the sample has none", () => {
  assert.equal(
    competitorGapExample(
      summary({ sample_intents: [{ topic: "x", commercial_stage: null, client_rank: 1, top_competitor_domain: null, top_competitor_name: null, top_competitor_rank: null }] }),
    ),
    null,
  );
});

test("competitorGapExample surfaces a real search the store missed and a competitor won", () => {
  const example = competitorGapExample(
    summary({
      sample_intents: [
        { topic: "أفضل قماش صيفي للثوب", commercial_stage: "consideration", client_rank: null, top_competitor_domain: "rival.sa", top_competitor_name: "منافس تجريبي", top_competitor_rank: 2 },
      ],
    }),
  );
  assert.deepEqual(example, { topic: "أفضل قماش صيفي للثوب", competitorName: "منافس تجريبي" });
});

test("revealBadge classifies seen/competitor/not_seen from real fields only", () => {
  assert.equal(revealBadge(4, null), "seen");
  assert.equal(revealBadge(null, "rival.sa"), "competitor");
  assert.equal(revealBadge(15, "rival.sa"), "competitor");
  assert.equal(revealBadge(null, null), "not_seen");
});

test("sanitizeMerchantText replaces SEO jargon leaking from backend-generated recommendation copy", () => {
  const text = sanitizeMerchantText("أنشئ صفحة تستهدف نية 'زيت السدر 5 لتر' مباشرة.");
  assert.doesNotMatch(text, /نية/);
  assert.match(text, /بحث/);
});

test("sanitizeMerchantText only replaces whole words, never a substring of a longer real word", () => {
  // "النوايا" contains "نية"-adjacent letters but must be replaced as its
  // own whole-word entry, not mangled by the shorter "نية"/"نوايا" patterns.
  const text = sanitizeMerchantText("راجعنا النوايا الشرائية للعميل.");
  assert.doesNotMatch(text, /النوايا/);
  assert.match(text, /عمليات البحث/);
});

test("sanitizeMerchantText leaves ordinary Arabic text untouched", () => {
  const text = "متجرك يظهر في نتائج بحث حقيقية.";
  assert.equal(sanitizeMerchantText(text), text);
});

test("competitorSharePercent returns null instead of dividing by an empty sample", () => {
  assert.equal(competitorSharePercent(3, 0), null);
});

test("competitorSharePercent computes a real rounded share", () => {
  assert.equal(competitorSharePercent(5, 10), 50);
  assert.equal(competitorSharePercent(1, 3), 33);
  assert.equal(competitorSharePercent(0, 10), 0);
});

test("revealBadgeLabel never shows raw jargon", () => {
  assert.equal(revealBadgeLabel("seen"), "ظهر متجرك");
  assert.equal(revealBadgeLabel("not_seen"), "لم يظهر متجرك");
  assert.match(revealBadgeLabel("competitor", "منافس تجريبي"), /منافس تجريبي بدلًا منك/);
});
