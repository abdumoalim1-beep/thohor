"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { getOpportunities, getRecommendations, OpportunityItem, RecommendationItem } from "@/lib/api";

export default function OpportunitiesPage() {
  const id = useParams<{ id: string }>().id;
  const [opportunities, setOpportunities] = useState<OpportunityItem[] | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.allSettled([getOpportunities(id), getRecommendations(id)]).then(([opportunityResult, recommendationResult]) => {
      if (opportunityResult.status === "rejected") { setError(String(opportunityResult.reason)); return; }
      setOpportunities(opportunityResult.value.opportunities);
      setRecommendations(recommendationResult.status === "fulfilled" ? recommendationResult.value.recommendations.filter((item) => item.opportunity_type.startsWith("ai_")) : []);
    });
  }, [id]);

  if (error) return <ErrorState message={error} />;
  if (!opportunities) return <LoadingState />;

  const aiOpportunityIds = new Set(recommendations.map((item) => item.opportunity_id));
  const aiOpportunities = opportunities.filter((item) => aiOpportunityIds.has(item.id));
  const qualified = aiOpportunities.filter((item) => recommendations.some((rec) => rec.opportunity_id === item.id && rec.is_primary));
  const pending = aiOpportunities.filter((item) => !qualified.includes(item));

  return <div className="space-y-7 pb-16">
    <header><p className="text-xs font-semibold text-primary">OPPORTUNITIES</p><h1 className="mt-1 text-3xl font-semibold">الفجوات المرصودة التي قد تقلل فرصة التوصية</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">لا نقول إننا نعرف السبب القطعي. نعرض فقط ما رصدناه في إجابات AI، وما يمكن إصلاحه، ومستوى الدليل المتوفر.</p></header>
    <Card className="border-primary/20 bg-primary-tint"><h2 className="font-semibold">بوابة أهلية الفرصة</h2><div className="mt-4 grid gap-2 sm:grid-cols-5">{["سؤال شراء حقيقي", "تطابق قوي", "بديل موصى به", "فجوة قابلة للإصلاح", "دليل كافٍ"].map((label, index) => <div key={label} className="rounded-xl bg-white p-3 text-center text-xs font-medium"><span className="mb-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-primary text-white">{index + 1}</span><p>{label}</p></div>)}</div><p className="mt-3 text-xs text-text-secondary">إذا لم نستطع تصنيف التوصية أو إثبات تطابق المنتج، تبقى النتيجة ملاحظة ولا تتحول إلى إجراء.</p></Card>
    <div className="flex items-center justify-between"><h2 className="font-semibold">فرص AI مؤهلة ({qualified.length})</h2><Link href={`/stores/${id}/actions`} className="text-sm font-semibold text-primary">الإجراءات الجاهزة</Link></div>
    <div className="grid gap-4 md:grid-cols-2">{qualified.map((item) => { const rec = recommendations.find((candidate) => candidate.opportunity_id === item.id && candidate.is_primary); return <Card key={item.id}><div className="flex justify-between gap-3"><Badge variant="primary">اجتازت بوابة الدليل</Badge><Badge variant="neutral">ثقة {Math.round(item.confidence * 100)}%</Badge></div><h3 className="mt-3 text-lg font-semibold">{item.title}</h3><p className="mt-2 text-sm leading-6 text-text-secondary">{item.description}</p>{rec && <Link href={`/stores/${id}/recommendations/${rec.id}`} className="mt-4 inline-block text-sm font-semibold text-primary">عرض الدليل والإجراء</Link>}</Card>; })}{!qualified.length && <Card><p className="text-sm text-text-tertiary">لا توجد فرصة AI اجتازت الدليل الكافي حاليًا.</p></Card>}</div>
    <details className="rounded-xl border border-border bg-white p-4"><summary className="cursor-pointer text-sm font-semibold">ملاحظات AI تحتاج دليلًا إضافيًا ({pending.length})</summary><div className="mt-4 space-y-3">{pending.map((item) => <div key={item.id} className="rounded-xl bg-bg-subtle p-3"><p className="text-sm font-medium">{item.title}</p><p className="mt-1 text-xs text-text-secondary">لم تجتز بعد جميع شروط فرصة قابلة للتنفيذ.</p></div>)}</div></details>
  </div>;
}
