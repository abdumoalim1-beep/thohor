import assert from "node:assert/strict";
import test from "node:test";

import type { ResearchRunSummary } from "./api.ts";
import {
  NO_PROGRESS_STALL_MS,
  PENDING_WORKER_NOTICE_MS,
  activeRunView,
  isTerminalRunStatus,
  parseApiTimestamp,
  runProgressFingerprint,
  shouldContinuePolling,
} from "./research-run-state.ts";

const START = Date.parse("2026-08-13T12:00:00.000Z");

function run(status: string, agentRuns: ResearchRunSummary["agent_runs"] = []): ResearchRunSummary {
  return {
    id: "run-1",
    run_type: "baseline",
    status,
    created_at: new Date(START).toISOString(),
    started_at: status === "pending" ? null : new Date(START).toISOString(),
    completed_at: ["completed", "failed", "cancelled"].includes(status)
      ? new Date(START + 1_000).toISOString()
      : null,
    error: null,
    agent_runs: agentRuns,
  };
}

test("completed, failed, and cancelled are terminal and stop polling", () => {
  for (const status of ["completed", "failed", "cancelled"]) {
    const value = run(status);
    assert.equal(isTerminalRunStatus(status), true);
    assert.equal(shouldContinuePolling(value, "progress"), false);
  }
});

test("an active run continues polling", () => {
  assert.equal(shouldContinuePolling(run("running"), "progress"), true);
});

test("pending changes to the worker-wait message after fifteen polling rounds", () => {
  const value = run("pending");
  assert.equal(
    activeRunView({
      run: value,
      nowMs: START + PENDING_WORKER_NOTICE_MS,
      firstObservedAtMs: START,
      lastProgressAtMs: START,
    }),
    "waiting_for_worker",
  );
  assert.equal(shouldContinuePolling(value, "waiting_for_worker"), true);
});

test("a run with no progress for the configured execution window becomes stalled and stops polling", () => {
  const value = run("running");
  const view = activeRunView({
    run: value,
    nowMs: START + NO_PROGRESS_STALL_MS,
    firstObservedAtMs: START,
    lastProgressAtMs: START,
  });
  assert.equal(view, "stalled");
  assert.equal(shouldContinuePolling(value, view), false);
});

test("completed stage findings change the progress payload immediately", () => {
  const before = run("running", [
    {
      agent_type: "crawl_agent_run",
      status: "running",
      started_at: new Date(START).toISOString(),
      completed_at: null,
      findings: null,
      error: null,
    },
  ]);
  const after = run("running", [
    {
      agent_type: "crawl_agent_run",
      status: "completed",
      started_at: new Date(START).toISOString(),
      completed_at: new Date(START + 2_000).toISOString(),
      findings: { pages_crawled: 12 },
      error: null,
    },
  ]);
  assert.notEqual(runProgressFingerprint(before), runProgressFingerprint(after));
  assert.deepEqual(after.agent_runs[0].findings, { pages_crawled: 12 });
});

test("naive backend timestamps are interpreted as UTC for stall detection", () => {
  assert.equal(parseApiTimestamp("2026-08-13T12:00:00"), START);
  assert.equal(parseApiTimestamp("2026-08-13T12:00:00Z"), START);
});
