import assert from "node:assert/strict";
import test from "node:test";
import type { IntentListItem } from "./api.ts";
import { groupSimilarSearches, isUsefulProductSearch, visibilityCounts, visibilityState } from "./search-visibility.ts";

const intent = (topic: string, rank: number | null, url: string | null = null): IntentListItem => ({ id: `${topic}-${rank}`, topic, category: "عيون", commercial_stage: null, estimated_demand: null, confidence: 0.8, source: "test", keywords: [], client_rank: rank, client_url: url });

test("visibility uses counts and keeps missing measurements distinct from no appearance", () => {
  assert.equal(visibilityState(intent("مسكرا", 2)), "top3");
  assert.equal(visibilityState(intent("كحل", null)), "insufficient");
  assert.equal(visibilityState(intent("آيلاينر", 50)), "not_seen");
  assert.equal(visibilityState({ ...intent("باليت", null), search_status: "measured", search_results_count: 10 }), "not_seen");
  assert.equal(visibilityState({ ...intent("تعذر", null), search_status: "failed" }), "failed");
  assert.deepEqual(visibilityCounts([intent("أ", 2), intent("ب", null)]), { top3: 1, top10: 0, top20: 0, not_seen: 0, failed: 0, insufficient: 1 });
});

test("similar search topics are grouped without inventing measurements", () => {
  const first = intent("مسكرا", 8);
  const second = { ...intent("مسكرا", 4), category: "منتجات العيون" };
  const grouped = groupSimilarSearches([first, second]);
  assert.equal(grouped.length, 1);
  assert.equal(grouped[0].client_rank, 4);
});

test("legal and generic navigation searches never become commercial priorities", () => {
  assert.equal(isUsefulProductSearch({ ...intent("استرجاع", null), category: "سياسة الاستبدال والاسترجاع" }), false);
  assert.equal(isUsefulProductSearch({ ...intent("تسوق", null), category: "المتجر" }), false);
  assert.equal(isUsefulProductSearch(intent("مسكرا", null)), true);
});
