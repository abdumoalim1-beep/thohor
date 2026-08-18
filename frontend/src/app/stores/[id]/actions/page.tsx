"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { LoadingState } from "@/components/ui/States";
import { getRecommendations, RecommendationItem } from "@/lib/api";

export default function ActionsPage() {
  const id = useParams<{ id: string }>().id;
  const [items, setItems] = useState<RecommendationItem[] | null>(null);

  useEffect(() => {
    getRecommendations(id)
      .then((result) => setItems(result.recommendations.filter((item) => item.is_primary && item.opportunity_type.startsWith("ai_"))))
      .catch(() => setItems([]));
  }, [id]);

  if (!items) return <LoadingState />;

  return <div className="space-y-6 pb-16">
    <header><p className="text-xs font-semibold text-primary">ACTIONS</p><h1 className="mt-1 text-3xl font-semibold">إجراءات مبنية على أدلة إجابات AI</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">لا نعرض هنا تحسينات SEO العامة. لا يتحول أي منتج إلى إجراء إلا إذا ارتبط بسؤال شراء وفجوة AI قابلة للإصلاح ودليل كافٍ.</p></header>
    <div className="space-y-4">{items.map((item) => <Link key={item.id} href={`/stores/${id}/recommendations/${item.id}`}><Card className="transition hover:border-primary/30"><div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex gap-2"><Badge variant="primary">إجراء جاهز للمراجعة</Badge><Badge variant="neutral">ثقة {item.confidence_tier === "high" ? "مرتفعة" : "متوسطة"}</Badge></div><h2 className="mt-3 text-lg font-semibold">{item.title}</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">{item.what_we_found}</p></div><span className="text-sm font-semibold text-primary">فتح الإجراء</span></div></Card></Link>)}{!items.length && <Card><p className="text-sm text-text-tertiary">لا توجد إجراءات AI اجتازت بوابة الدليل حاليًا. لن نملأ القائمة بتحسينات عامة.</p></Card>}</div>
  </div>;
}
