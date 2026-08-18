import assert from "node:assert/strict";
import test from "node:test";

import type { IntentListItem, StoreUnderstanding } from "./api.ts";
import { estimatedDemandLabel, storeUncertainties, summarizeIntents } from "./product-insights.ts";
import { buildMarketMap, storeIdentitySignals } from "./market-position.ts";

function intent(overrides: Partial<IntentListItem> = {}): IntentListItem {
  return {
    id: "intent-1",
    topic: "أفضل ماكينة قهوة",
    category: "القهوة",
    commercial_stage: "consideration",
    estimated_demand: "medium",
    confidence: 0.8,
    source: "catalog",
    keywords: [],
    client_rank: null,
    client_url: null,
    ...overrides,
  };
}

test("intent summary counts observed records without presenting them as buyers or purchases", () => {
  const summary = summarizeIntents([
    intent({ id: "1", commercial_stage: "purchase", estimated_demand: "high", client_rank: 7 }),
    intent({ id: "2", topic: "أنواع القهوة", commercial_stage: "awareness", estimated_demand: "low" }),
  ]);

  assert.deepEqual(summary, {
    topics: 2,
    purchase: 1,
    highEstimatedDemand: 1,
    visibleInTop10: 1,
    byStage: { awareness: 1, consideration: 0, purchase: 1, unknown: 0 },
  });
  assert.equal(estimatedDemandLabel("high"), "طلب تقديري مرتفع");
  assert.doesNotMatch(estimatedDemandLabel("high"), /عميل|مشتري|عملية شراء/);
});

test("store copy explicitly preserves unknown knowledge and never invents an audience", () => {
  const understanding: StoreUnderstanding = {
    understanding_stage: "partial",
    display_name: null,
    description: null,
    url: "https://example.test",
    business_type: null,
    country: null,
    city: null,
    primary_categories: [],
    target_audience: ["قيمة غير مدعومة يجب ألا تُعرض"],
    classification_confidence: null,
    classification_skipped: false,
    identity_source: null, identity_confidence: null, catalog_status: "pending",
    catalog_products_found: 0, competitor_discovery_status: "pending", suggested_competitors: [],
    pages_crawled: 2,
    products_found: 0,
    categories_found: 0,
    brands_found: 0,
    top_categories: [],
    product_samples: [],
    category_previews: [], product_count_status: "unavailable", estimated_products_count: null,
    sold_brands: [], business_info: [], audience_basis: null,
    brand: null,
    last_analyzed_at: null,
  };

  const copy = storeUncertainties(understanding).join(" ");
  assert.match(copy, /لم نتأكد/);
  assert.match(copy, /لا توجد بيانات كافية.*الجمهور أو حجم الطلب/);
  assert.doesNotMatch(copy, /قيمة غير مدعومة/);
});

test("observed product previews are not described as no products", () => {
  const understanding: StoreUnderstanding = {
    understanding_stage: "ready", display_name: "متجر", url: "https://example.test", business_type: "تجميل",
    country: null, city: null,
    primary_categories: ["مكياج"], target_audience: [], classification_confidence: 0.8, classification_skipped: false,
    identity_source: null, identity_confidence: null, catalog_status: "ready",
    catalog_products_found: 0, competitor_discovery_status: "pending", suggested_competitors: [],
    pages_crawled: 10, products_found: 0, categories_found: 0, brands_found: 1, top_categories: [],
    product_samples: [{ id: "preview", name: "مسكرا", url: "https://example.test/p/1", category_name: null, price: null, currency: null, image_url: "https://example.test/p.jpg", detail_available: false }],
    description: null, category_previews: [], product_count_status: "unavailable", estimated_products_count: null,
    sold_brands: [], business_info: [], audience_basis: null,
    brand: null, last_analyzed_at: null,
  };
  const copy = storeUncertainties(understanding).join(" ");
  assert.match(copy, /رصدنا أسماء وصور منتجات/);
  assert.doesNotMatch(copy, /لم نستخرج منتجات محددة/);
});

test("store identity signals use only observed catalog fields", () => {
  const understanding = {
    understanding_stage: "ready", display_name: "متجر", url: "https://example.test", business_type: "أثاث",
    country: null, city: null,
    primary_categories: ["غرف نوم", "مجالس"], target_audience: ["عائلات"], classification_confidence: 0.8, classification_skipped: false,
    identity_source: null, identity_confidence: null, catalog_status: "ready",
    catalog_products_found: 20, competitor_discovery_status: "pending", suggested_competitors: [],
    pages_crawled: 10, products_found: 20, categories_found: 2, brands_found: 3, top_categories: [], product_samples: [],
    description: null, category_previews: [], product_count_status: "confirmed", estimated_products_count: null,
    sold_brands: [], business_info: [], audience_basis: null,
    brand: null, last_analyzed_at: null,
  } satisfies StoreUnderstanding;
  const signals = storeIdentitySignals(understanding).join(" ");
  assert.match(signals, /أثاث/);
  assert.match(signals, /20 منتجًا/);
  assert.doesNotMatch(signals, /عائلات/);
});

test("market map always distinguishes the store from market entities", () => {
  const entities = buildMarketMap([], [intent({ client_rank: 4 })]);
  assert.deepEqual(entities.map((entity) => entity.kind), ["store"]);
  assert.equal(entities[0].label, "متجرك");
});
