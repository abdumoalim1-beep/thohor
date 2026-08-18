// Part R6 (Round 1 remediation) — shared human-readable labels for
// Competitor.classification (app/competitors/classification.py). Used
// anywhere a competitor/domain is rendered (Competitors page, Market/
// Cross-Surface, Recommendation evidence) so the same domain always reads
// the same way, and a non-business entity (publisher, marketplace, ...)
// never gets framed as a direct competitor.

export const CLASSIFICATION_LABELS: Record<string, string> = {
  direct_competitor: "منافس مباشر",
  retailer: "بائع تجزئة (غير مؤكَّد كمنافس)",
  marketplace: "سوق إلكتروني عام",
  wholesale: "منصة جملة (B2B)",
  social: "منصة تواصل اجتماعي",
  forum: "منتدى/مجتمع",
  video: "منصة فيديو",
  publisher: "مصدر معلومات/نشر",
  government: "جهة حكومية",
  educational: "جهة تعليمية",
  irrelevant: "غير ذي صلة تجاريًا",
  unknown: "غير مصنَّف",
};

export function classificationLabel(classification: string): string {
  return CLASSIFICATION_LABELS[classification] ?? classification;
}
