import type { ResearchRunSummary } from "@/lib/api";

export const POLL_INTERVAL_MS = 2_000;
export const TERMINAL_RUN_STATUSES = new Set(["completed", "failed", "cancelled"]);

// A Celery task claims a pending row before doing any research work. Thirty
// seconds (15 normal polling rounds) is therefore enough to stop presenting
// queue time as active analysis, while still allowing normal broker startup.
export const PENDING_WORKER_NOTICE_MS = 30_000;

// The only configured wall-clock execution ceiling is the iterative research
// budget (600s). Add five minutes for the fixed crawl/measurement phases and
// queue/database overhead. With no backend heartbeat, 15 minutes without any
// status/findings change is the most conservative evidence we have for a stall.
export const NO_PROGRESS_STALL_MS = 15 * 60_000;

export type ActiveRunView = "progress" | "waiting_for_worker" | "stalled";

export function isTerminalRunStatus(status: string | undefined): boolean {
  return status != null && TERMINAL_RUN_STATUSES.has(status);
}

export function runProgressFingerprint(run: ResearchRunSummary): string {
  return JSON.stringify({
    status: run.status,
    agent_runs: run.agent_runs.map((agentRun) => ({
      agent_type: agentRun.agent_type,
      status: agentRun.status,
      started_at: agentRun.started_at,
      completed_at: agentRun.completed_at,
      findings: agentRun.findings,
      error: agentRun.error,
    })),
  });
}

export function latestRunProgressAtMs(run: ResearchRunSummary): number {
  const timestamps = [
    run.created_at,
    run.started_at,
    ...run.agent_runs.flatMap((agentRun) => [agentRun.started_at, agentRun.completed_at]),
  ]
    .filter((value): value is string => value != null)
    .map(parseApiTimestamp)
    .filter(Number.isFinite);
  return timestamps.length > 0 ? Math.max(...timestamps) : Date.now();
}

export function parseApiTimestamp(value: string | null | undefined): number {
  if (!value) return Number.NaN;
  // Backend timestamps are UTC. Older running API processes may serialize a
  // naive ISO value, so preserve compatibility until they are restarted.
  const explicitZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`;
  return Date.parse(explicitZone);
}

export function activeRunView({
  run,
  nowMs,
  firstObservedAtMs,
  lastProgressAtMs,
}: {
  run: ResearchRunSummary;
  nowMs: number;
  firstObservedAtMs: number;
  lastProgressAtMs: number;
}): ActiveRunView {
  if (nowMs - lastProgressAtMs >= NO_PROGRESS_STALL_MS) return "stalled";
  if (run.status === "pending" && nowMs - firstObservedAtMs >= PENDING_WORKER_NOTICE_MS) {
    return "waiting_for_worker";
  }
  return "progress";
}

export function shouldContinuePolling(run: ResearchRunSummary, view: ActiveRunView): boolean {
  return !isTerminalRunStatus(run.status) && view !== "stalled";
}

export function simplifyRunError(error: string | null): string | null {
  if (!error) return null;
  const withoutStepPrefix = error.replace(/^[a-z0-9_]+ failed:\s*/i, "").trim();
  if (!withoutStepPrefix) return null;
  return withoutStepPrefix.length > 180 ? `${withoutStepPrefix.slice(0, 177)}…` : withoutStepPrefix;
}
