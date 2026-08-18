"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { StoreDetail, getStore } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { ErrorState, LoadingState } from "@/components/ui/States";

const STORE_STATUS_LABELS: Record<string, string> = {
  active: "نشط",
  pending: "قيد الإعداد",
  paused: "متوقف مؤقتًا",
};

export default function SettingsPage() {
  const params = useParams<{ id: string }>();
  const storeId = params.id;

  const [detail, setDetail] = useState<StoreDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await getStore(storeId);
        if (!cancelled) setDetail(res);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [storeId]);

  if (error) return <ErrorState message={error} />;
  if (!detail) return <LoadingState />;

  return (
    <div className="flex max-w-lg flex-col gap-8">
      <div>
        <h1 className="text-xl font-bold text-text">الإعدادات</h1>
        <p className="mt-1 text-sm text-text-secondary">معلومات متجرك الأساسية.</p>
      </div>

      <Card padding="lg">
        <dl className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-3">
            <dt className="text-sm text-text-secondary">رابط المتجر</dt>
            <dd dir="ltr" className="text-sm font-medium text-text">
              {detail.url}
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-border pt-4">
            <dt className="text-sm text-text-secondary">الحالة</dt>
            <dd>
              <Badge variant={detail.status === "active" ? "success" : "neutral"}>
                {STORE_STATUS_LABELS[detail.status] ?? detail.status}
              </Badge>
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-border pt-4">
            <dt className="text-sm text-text-secondary">صفحات مفهرسة</dt>
            <dd className="tabular text-sm font-medium text-text">{detail.pages_crawled}</dd>
          </div>
        </dl>
      </Card>

      <p className="text-sm text-text-tertiary">
        إعدادات جدولة المراقبة والتنبيهات المتقدمة ستتوفر هنا قريبًا.
      </p>
    </div>
  );
}
