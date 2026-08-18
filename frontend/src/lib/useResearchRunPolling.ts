"use client";

import { useCallback, useEffect, useState } from "react";

import { StoreDetail, getStore } from "@/lib/api";
import {
  ActiveRunView,
  POLL_INTERVAL_MS,
  activeRunView,
  isTerminalRunStatus,
  latestRunProgressAtMs,
  parseApiTimestamp,
  shouldContinuePolling,
} from "@/lib/research-run-state";

export function useResearchRunPolling(storeId: string) {
  const [store, setStore] = useState<StoreDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runView, setRunView] = useState<ActiveRunView>("progress");
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => {
    setError(null);
    setRunView("progress");
    setRefreshKey((value) => value + 1);
  }, []);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const result = await getStore(storeId);
        if (disposed) return;
        setStore(result);

        const run = result.latest_run;
        if (!run || isTerminalRunStatus(run.status)) {
          setRunView("progress");
          return;
        }

        const nowMs = Date.now();
        const view = activeRunView({
          run,
          nowMs,
          firstObservedAtMs: Number.isFinite(parseApiTimestamp(run.created_at))
            ? parseApiTimestamp(run.created_at)
            : nowMs,
          lastProgressAtMs: latestRunProgressAtMs(run),
        });
        setRunView(view);
        if (shouldContinuePolling(run, view)) timer = setTimeout(poll, POLL_INTERVAL_MS);
      } catch (caught) {
        if (!disposed) setError(caught instanceof Error ? caught.message : String(caught));
      }
    };

    poll();
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
    };
  }, [storeId, refreshKey]);

  return { store, error, runView, refresh };
}
