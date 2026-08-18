"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { getAlerts } from "@/lib/api";
import { Sidebar } from "@/components/ui/Sidebar";
import { Topbar } from "@/components/ui/Topbar";
import { StoreProgressProvider, useStoreProgressContext } from "@/components/ui/StoreProgressProvider";

export default function StoreLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ id: string }>();
  const storeId = params.id;

  return (
    <StoreProgressProvider storeId={storeId}>
      <StoreShell storeId={storeId}>{children}</StoreShell>
    </StoreProgressProvider>
  );
}

function StoreShell({ storeId, children }: { storeId: string; children: React.ReactNode }) {
  const { detail, isRunning, completedSteps, totalSteps } = useStoreProgressContext();
  const [unreadCount, setUnreadCount] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const alertsRes = await getAlerts(storeId);
        if (!cancelled) setUnreadCount(alertsRes.alerts.filter((a) => a.status === "unread").length);
      } catch {
        // Chrome context is non-critical — pages render their own errors.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [storeId]);

  const lastUpdatedAt = detail?.latest_run?.completed_at ?? detail?.latest_run?.started_at ?? null;

  return (
    <div className="mersad-workspace flex h-screen w-full overflow-hidden bg-bg pt-9 text-text">
      <div className="hidden md:flex">
        <Sidebar storeId={storeId} />
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div className="w-[17.5rem] shrink-0">
            <Sidebar storeId={storeId} />
          </div>
          <button
            aria-label="إغلاق القائمة"
            onClick={() => setMobileOpen(false)}
            className="flex-1 bg-black/30"
          />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          storeUrl={detail?.url}
          lastUpdatedAt={lastUpdatedAt}
          unreadCount={unreadCount}
          storeId={storeId}
          onMenuClick={() => setMobileOpen(true)}
          progress={isRunning ? { completedSteps, totalSteps } : null}
        />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-7xl px-4 py-7 sm:px-7 sm:py-10">{children}</div>
        </main>
      </div>
    </div>
  );
}
