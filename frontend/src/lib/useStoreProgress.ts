import { useEffect, useState } from "react";

import { StoreDetail, StoreUnderstanding, getStore, getStoreUnderstanding } from "@/lib/api";
import { AGENT_TYPE_LABELS } from "@/components/ui/labels";

const TERMINAL_STATUSES = new Set(["completed", "failed"]);
const POLL_INTERVAL_MS = 2000;
const TOTAL_STEPS = Object.keys(AGENT_TYPE_LABELS).length;

export type StoreProgress = {
  detail: StoreDetail | null;
  understanding: StoreUnderstanding | null;
  error: string | null;
  isRunning: boolean;
  completedSteps: number;
  totalSteps: number;
  refresh: () => void;
};

/** Single shared poll of GET /stores/{id} (+ /understanding while a run is
 * in progress), replacing what used to be two independent 2s polling loops
 * (layout.tsx's one-shot chrome fetch and Overview's own loop) so the
 * Topbar chip, the "متجرك" page, and Overview all read one consistent
 * result instead of racing each other. */
export function useStoreProgress(storeId: string): StoreProgress {
  const [detail, setDetail] = useState<StoreDetail | null>(null);
  const [understanding, setUnderstanding] = useState<StoreUnderstanding | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      try {
        const result = await getStore(storeId);
        if (cancelled) return;
        setDetail(result);

        const runStatus = result.latest_run?.status;
        const running = !!runStatus && !TERMINAL_STATUSES.has(runStatus);

        if (runStatus) {
          try {
            const understandingResult = await getStoreUnderstanding(storeId);
            if (!cancelled) setUnderstanding(understandingResult);
          } catch {
            // Understanding is a progressive enhancement — a transient
            // failure here must not block the run-status poll loop.
          }
        }

        if (running) {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    };

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [storeId, refreshKey]);

  const runStatus = detail?.latest_run?.status;
  const isRunning = detail?.latest_run != null && !!runStatus && !TERMINAL_STATUSES.has(runStatus);
  const completedSteps = (detail?.latest_run?.agent_runs ?? []).filter(
    (a) => a.status === "completed" || a.status === "failed"
  ).length;

  return {
    detail,
    understanding,
    error,
    isRunning,
    completedSteps,
    totalSteps: TOTAL_STEPS,
    refresh: () => setRefreshKey((k) => k + 1),
  };
}
