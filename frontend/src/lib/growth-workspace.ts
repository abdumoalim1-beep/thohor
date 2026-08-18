import type { IntentListItem, PageWorkspaceItem, ProductWorkspaceListItem } from "./api";

export type AuditLevel = "ready" | "review" | "unavailable";
export type AuditItem = { key: string; label: string; level: AuditLevel; detail: string };

export function buildTechnicalAudit(pages: PageWorkspaceItem[], storeUrl: string): AuditItem[] {
  const home = pages.find((page) => page.page_type === "home");
  const withTitles = pages.filter((page) => Boolean(page.title?.trim())).length;
  const withH1 = pages.filter((page) => Boolean(page.h1?.trim())).length;
  const duplicateTitles = pages.length - new Set(pages.map((page) => page.title?.trim()).filter(Boolean)).size;
  return [
    { key: "https", label: "اتصال HTTPS", level: storeUrl.startsWith("https://") ? "ready" : "review", detail: storeUrl.startsWith("https://") ? "المتجر يستخدم اتصالًا مشفرًا." : "الرابط المرصود لا يبدأ بـ HTTPS." },
    { key: "home", label: "الصفحة الرئيسية", level: home ? "ready" : "review", detail: home ? "تم اكتشاف الصفحة الرئيسية." : "لم نتمكن من تحديد الصفحة الرئيسية ضمن الصفحات المرصودة." },
    { key: "titles", label: "عناوين الصفحات", level: pages.length && withTitles === pages.length ? "ready" : "review", detail: `${withTitles} من ${pages.length} صفحة مرصودة لديها عنوان.` },
    { key: "h1", label: "العناوين الرئيسية H1", level: pages.length && withH1 === pages.length ? "ready" : "review", detail: `${withH1} من ${pages.length} صفحة مرصودة لديها H1.` },
    { key: "duplicates", label: "تكرار العناوين", level: duplicateTitles === 0 ? "ready" : "review", detail: duplicateTitles ? `وجدنا ${duplicateTitles} عناوين مكررة ضمن العينة المرصودة.` : "لم يظهر تكرار في العناوين المرصودة." },
    { key: "sitemap", label: "Sitemap والفهرسة", level: "unavailable", detail: "لم يُربط Google Search Console؛ يمكن تجهيز الملف وفحصه، لكن لا ندّعي إرساله أو فهرسته." },
    { key: "analytics", label: "بيانات الزيارات والتحويل", level: "unavailable", detail: "لا توجد بيانات Analytics مربوطة؛ لا نعرض زيارات أو مبيعات تقديرية." },
  ];
}

export function buildLlmsTxt(store: { name?: string | null; url: string; description?: string | null }, pages: PageWorkspaceItem[]): string {
  const important = pages.filter((page) => ["home", "category", "product", "content"].includes(page.page_type)).slice(0, 100);
  const lines = [`# ${store.name?.trim() || new URL(store.url).hostname}`, "", `> ${store.description?.trim() || "وصف المتجر غير مؤكد بعد."}`, "", `- الموقع: ${store.url}`, "", "## الصفحات المرصودة"];
  for (const page of important) lines.push(`- [${page.h1 || page.title || page.page_type}](${page.url})`);
  lines.push("", "> هذا الملف مبني على صفحات رصدها ظهور، ويحتاج مراجعة التاجر قبل النشر.");
  return lines.join("\n");
}

export function buildOrganizationSchema(store: { name?: string | null; url: string; description?: string | null }) {
  return { "@context": "https://schema.org", "@type": "Organization", name: store.name?.trim() || new URL(store.url).hostname, url: store.url, ...(store.description?.trim() ? { description: store.description.trim() } : {}) };
}

export function buildBulkCsv(products: ProductWorkspaceListItem[]): string {
  const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const rows = [["id", "name", "url", "category", "completion_score", "issues_count", "suggested_action"], ...products.map((product) => [product.id, product.name, product.url, product.category_name, product.completion_score, product.issues_count, product.issues_count ? "مراجعة صفحة المنتج" : "لا إجراء أساسي"] )];
  return rows.map((row) => row.map(escape).join(",")).join("\n");
}

export function keywordStatus(intent: IntentListItem): { label: string; kind: "good" | "gap" | "pending" } {
  if (intent.search_status === "failed" || intent.search_status === "not_tested") return { label: "لم يكتمل القياس", kind: "pending" };
  if (intent.client_rank !== null && intent.client_rank <= 10) return { label: `ضمن أول 10 (#${intent.client_rank})`, kind: "good" };
  return { label: intent.client_rank ? `يظهر في المركز ${intent.client_rank}` : "لم يظهر ضمن النطاق المرصود", kind: "gap" };
}

export function contentIdeas(intents: IntentListItem[]) {
  return intents.filter((item) => item.commercial_stage !== "purchase" || item.client_rank === null || item.client_rank > 10).slice(0, 20).map((item) => ({
    id: item.id,
    title: `دليل ${item.topic}`,
    topic: item.topic,
    stage: item.commercial_stage,
    evidence: item.client_rank === null ? "لم يظهر المتجر ضمن النطاق المرصود لهذه العملية." : `أفضل ظهور مرصود للمتجر هو المركز ${item.client_rank}.`,
    outline: ["مقدمة تجيب عن السؤال مباشرة", `ما الذي يجب معرفته عن ${item.topic}`, "معايير الاختيار", "أسئلة شائعة", "روابط إلى المنتجات أو التصنيفات المناسبة"],
  }));
}
