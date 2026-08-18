"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { FindingItem, ResearchTaskItem, getFindings, getResearchTasks, triggerResearchRun } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { StatMetric } from "@/components/ui/StatMetric";
import { CancelledResearchState, FailedResearchState, StalledResearchState } from "@/components/ui/ResearchRunState";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { agentTypeLabel } from "@/components/ui/labels";
import { simplifyRunError } from "@/lib/research-run-state";
import { useResearchRunPolling } from "@/lib/useResearchRunPolling";

const FINDING_STATUS_LABELS: Record<string, string> = {
  candidate: "مرشّح",
  validated: "مُتحقَّق منه",
  rejected: "مرفوض",
};

const STATUS_TEXT_CLASS: Record<string, string> = {
  completed: "text-success",
  failed: "text-danger",
  skipped_duplicate: "text-text-tertiary",
};

export default function ResearchDetailPage() {
  const params = useParams<{ id: string }>();
  const storeId = params.id;

  const { store, error, runView, refresh } = useResearchRunPolling(storeId);
  const [tasks, setTasks] = useState<ResearchTaskItem[]>([]);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [detailsError, setDetailsError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!store) return;
    (async () => {
      try {
        const [tasksRes, findingsRes] = await Promise.all([getResearchTasks(storeId), getFindings(storeId)]);
        if (cancelled) return;
        setTasks(tasksRes.tasks);
        setFindings(findingsRes.findings);
        setDetailsError(null);
      } catch (caught) {
        if (!cancelled) setDetailsError(caught instanceof Error ? caught.message : String(caught));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [store, storeId]);

  const retry = async () => {
    setRetrying(true);
    setDetailsError(null);
    try {
      await triggerResearchRun(storeId);
      refresh();
    } catch (caught) {
      setDetailsError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRetrying(false);
    }
  };

  if (error) return <ErrorState message={error} />;
  if (!store) return <LoadingState />;

  const run = store.latest_run;
  if (runView === "stalled") return <StalledResearchState onCheckAgain={refresh} />;
  if (run?.status === "failed") {
    return (
      <div className="flex flex-col gap-3">
        <FailedResearchState reason={simplifyRunError(run.error)} onRetry={retry} retrying={retrying} />
        {detailsError && <ErrorState message={detailsError} />}
      </div>
    );
  }
  if (run?.status === "cancelled") return <CancelledResearchState />;

  const summary = store.research_summary;

  return (
    <div className="flex flex-col gap-8">
      <section>
        <h1 className="text-xl font-bold text-text">تفاصيل البحث (متقدّم)</h1>
        {store.latest_run && (
          <p className="mt-1 text-sm text-text-secondary">
            آخر تشغيل: {store.latest_run.run_type} — {store.latest_run.status}
            {store.latest_run.completed_at && ` — ${new Date(store.latest_run.completed_at).toLocaleString("ar")}`}
          </p>
        )}
      </section>

      {detailsError && <ErrorState message={detailsError} />}

      {summary && (
        <section>
          <h2 className="mb-3 text-base font-semibold text-text">التكاليف والإحصائيات</h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatMetric label="إجمالي المهام" value={String(summary.total_tasks)} />
            <StatMetric label="عمق البحث" value={String(summary.research_depth_reached)} />
            <StatMetric label="استعلامات بحث" value={String(summary.search_queries_executed)} />
            <StatMetric label="محادثات AI" value={String(summary.ai_conversations_executed)} />
            <StatMetric label="صفحات مزحوفة" value={String(summary.pages_crawled)} />
            <StatMetric label="صفحات منافسين محلَّلة" value={String(summary.competitor_pages_analyzed)} />
            <StatMetric label="سجلات أدلة" value={String(summary.evidence_records)} />
            <StatMetric label="التكلفة الإجمالية" value={`$${summary.total_cost_usd.toFixed(4)}`} />
          </div>
        </section>
      )}

      {store.latest_run && store.latest_run.agent_runs.length > 0 && (
        <section>
          <h2 className="mb-3 text-base font-semibold text-text">خطوات التشغيل</h2>
          <ul className="flex flex-col gap-2">
            {store.latest_run.agent_runs.map((a) => (
              <li key={a.agent_type}>
                <Card padding="sm" className="flex items-center justify-between text-sm">
                  <span className="text-text">{agentTypeLabel(a.agent_type)}</span>
                  <span className={STATUS_TEXT_CLASS[a.status] ?? "text-text-tertiary"}>{a.status}</span>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      {tasks.length > 0 && (
        <section>
          <h2 className="mb-3 text-base font-semibold text-text">شجرة مهام البحث ({tasks.length})</h2>
          <ul className="flex flex-col gap-1 font-mono text-xs">
            {tasks.map((t) => (
              <li key={t.id} style={{ paddingInlineStart: `${t.depth * 1.5}rem` }}>
                <Card padding="sm">
                  <span className="text-text-tertiary">{"└ ".repeat(t.depth > 0 ? 1 : 0)}</span>
                  <span className="font-semibold text-text">{t.task_type}</span>{" "}
                  <span
                    className={
                      t.status === "completed"
                        ? "text-success"
                        : t.status === "failed"
                          ? "text-danger"
                          : t.status === "skipped_duplicate"
                            ? "text-text-tertiary"
                            : "text-warning"
                    }
                  >
                    [{t.status}]
                  </span>{" "}
                  {t.result_summary && <span className="text-text-secondary">— {t.result_summary}</span>}
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      {findings.length > 0 && (
        <section>
          <h2 className="mb-3 text-base font-semibold text-text">الاستنتاجات (Findings)</h2>
          <ul className="flex flex-col gap-2">
            {findings.map((f) => (
              <li key={f.id}>
                <Card padding="sm">
                  <p className="text-sm text-text">{f.statement}</p>
                  <div className="mt-1.5 flex gap-3 text-xs text-text-tertiary">
                    <span>{FINDING_STATUS_LABELS[f.status] ?? f.status}</span>
                    <span>الثقة: {Math.round(f.confidence * 100)}%</span>
                    <span>تحققات: {f.validation_count}</span>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
