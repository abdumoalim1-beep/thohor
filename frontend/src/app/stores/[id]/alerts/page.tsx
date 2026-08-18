"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AlertItem, getAlerts, patchAlertStatus } from "@/lib/api";
import { ChangeFeed } from "@/components/ui/ChangeFeed";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { IconBell } from "@/components/ui/icons";

export default function AlertsPage() {
  const params = useParams<{ id: string }>();
  const storeId = params.id;

  const [alerts, setAlerts] = useState<AlertItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await getAlerts(storeId);
        if (!cancelled) setAlerts(res.alerts);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [storeId]);

  const markRead = async (alertId: string) => {
    try {
      const updated = await patchAlertStatus(alertId, "read");
      setAlerts((prev) => prev?.map((a) => (a.id === alertId ? updated : a)) ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (error) return <ErrorState message={error} />;
  if (!alerts) return <LoadingState />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-text">التنبيهات</h1>
        <p className="mt-1 text-sm text-text-secondary">كل تغيّر ملحوظ في ظهورك، بترتيب زمني.</p>
      </div>
      {alerts.length === 0 ? (
        <EmptyState icon={<IconBell className="h-5 w-5" />} title="لا توجد تنبيهات بعد" description="سنعلمك فور اكتشاف تغيّر مهم في ظهورك." />
      ) : (
        <ChangeFeed alerts={alerts} storeId={storeId} onMarkRead={markRead} />
      )}
    </div>
  );
}
