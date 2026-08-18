"use client";

import { useParams } from "next/navigation";

import { StoreUnderstandingCard } from "@/components/ui/StoreUnderstandingCard";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { LinkButton } from "@/components/ui/Button";
import { IconPrint, IconStore } from "@/components/ui/icons";
import { useStoreProgressContext } from "@/components/ui/StoreProgressProvider";

export default function StorePage() {
  const params = useParams<{ id: string }>();
  const storeId = params.id;

  const { detail, understanding, error } = useStoreProgressContext();

  if (error) return <ErrorState message={error} />;
  if (!detail) return <LoadingState />;

  const stage = understanding?.understanding_stage ?? "pending";

  if (stage === "pending") {
    return (
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-xl font-bold text-text">متجرك</h1>
          <p className="mt-1 text-sm text-text-secondary">كيف يفهم ظهور نشاطك ومنتجاتك.</p>
        </div>
        <LoadingState label="نقرأ صفحات متجرك الآن..." />
      </div>
    );
  }

  if (stage === "failed" || !understanding) {
    return (
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-xl font-bold text-text">متجرك</h1>
          <p className="mt-1 text-sm text-text-secondary">كيف يفهم ظهور نشاطك ومنتجاتك.</p>
        </div>
        <EmptyState
          icon={<IconStore className="h-5 w-5" />}
          title="تعذّر قراءة متجرك"
          description="واجهنا مشكلة أثناء قراءة صفحات متجرك. يمكنك إعادة تشغيل التحليل من صفحة الإعدادات."
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-text">متجرك</h1>
          <p className="mt-1 text-sm text-text-secondary">كيف يفهم ظهور نشاطك ومنتجاتك — هذه هي البيانات الحقيقية التي اكتشفناها.</p>
        </div>
        <LinkButton href={`/stores/${storeId}/reports`} variant="secondary" size="sm">
          <IconPrint className="h-4 w-4" />
          تصدير تقرير
        </LinkButton>
      </div>
      <StoreUnderstandingCard understanding={understanding} storeId={storeId} />
    </div>
  );
}
