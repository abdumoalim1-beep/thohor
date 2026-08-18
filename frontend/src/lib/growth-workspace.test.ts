import assert from "node:assert/strict";
import test from "node:test";
import { buildLlmsTxt, buildOrganizationSchema, keywordStatus } from "./growth-workspace.ts";

test("keyword status never presents an intent as buyers or purchases", () => {
  const result = keywordStatus({ id:"1", topic:"أحذية", category:null, commercial_stage:"purchase", estimated_demand:"high", confidence:1, source:"observed", keywords:[], client_rank:null, client_url:null, search_status:"measured" });
  assert.equal(result.label, "لم يظهر ضمن النطاق المرصود");
  assert.doesNotMatch(result.label, /عميل|مشتري|شراء|عملية بيع/);
});

test("generated artifacts do not invent unknown store description", () => {
  const store = { name:null, url:"https://example.com", description:null };
  assert.match(buildLlmsTxt(store, []), /وصف المتجر غير مؤكد بعد/);
  assert.equal("description" in buildOrganizationSchema(store), false);
});
