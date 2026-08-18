"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { RecommendationItem, getRecommendations } from "@/lib/api";

export default function RecommendationsPage() {
  const storeId = useParams<{ id: string }>().id;
  const [items, setItems] = useState<RecommendationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getRecommendations(storeId)
      .then((result) => setItems(result.recommendations.filter((item) => !["dismissed", "superseded"].includes(item.status))))
      .catch((reason) => setError(String(reason)));
  }, [storeId]);

  if (error) return <ErrorState message={error} />;
  if (!items) return <LoadingState />;

  const qualified = items.filter((item) => item.is_primary);
  const supporting = items.filter((item) => !item.is_primary);

  return (
    <div className="space-y-7 pb-16">
      <header>
        <p className="text-xs font-semibold text-primary">ACTIONS</p>
        <h1 className="mt-1 text-3xl font-semibold text-text">إجراءات لتحسين فرصة توصية منتجاتك</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
          كل إجراء يبدأ بفجوة مرصودة ودليل محفوظ. لا نفترض أن الفجوة هي السبب القطعي لغيابك، ولا نعد بظهور أو مبيعات بعد التنفيذ.
        </p>
      </header>

      <Card className="border-primary/20 bg-primary-tint">
        <p className="text-sm leading-6 text-text-secondary">
          القياس الصحيح بعد التنفيذ هو إعادة السؤال عدة مرات ومقارنة معدل الذكر والتوصية والاستشهاد وثبات المعلومة، وليس نتيجة اختبار واحد.
        </p>
      </Card>

      <section>
        <h2 className="mb-3 font-semibold text-text">جاهزة للمراجعة ({qualified.length})</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          {qualified.map((item) => <ActionCard key={item.id} storeId={storeId} item={item} />)}
          {!qualified.length && <Card><p className="text-sm text-text-tertiary">لا يوجد إجراء اجتاز بوابة الدليل حاليًا.</p></Card>}
        </div>
      </section>

      {!!supporting.length && (
        <details className="rounded-xl border border-border bg-white p-4">
          <summary className="cursor-pointer text-sm font-semibold text-text">ملاحظات تحتاج دليلًا إضافيًا ({supporting.length})</summary>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {supporting.map((item) => <ActionCard key={item.id} storeId={storeId} item={item} pending />)}
          </div>
        </details>
      )}
    </div>
  );
}

function ActionCard({ storeId, item, pending = false }: { storeId: string; item: RecommendationItem; pending?: boolean }) {
  return (
    <Card className="flex h-full flex-col">
      <div className="flex flex-wrap gap-2">
        <Badge variant={pending ? "neutral" : "primary"}>{pending ? "تحتاج دليلًا إضافيًا" : "إجراء مؤهل"}</Badge>
        <Badge variant="neutral">ثقة {item.confidence_tier === "high" ? "مرتفعة" : item.confidence_tier === "medium" ? "متوسطة" : "منخفضة"}</Badge>
      </div>
      <h3 className="mt-3 text-lg font-semibold text-text">{item.title}</h3>
      <p className="mt-2 flex-1 text-sm leading-6 text-text-secondary">{item.what_we_found || item.why_this_improvement}</p>
      <Link href={`/stores/${storeId}/recommendations/${item.id}`} className="mt-5 text-sm font-semibold text-primary">عرض الاستنتاج والدليل والتنفيذ</Link>
    </Card>
  );
}
