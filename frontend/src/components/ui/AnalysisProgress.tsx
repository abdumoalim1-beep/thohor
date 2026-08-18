import type { ResearchRunSummary, StoreDetail } from "@/lib/api";
import { IconCheckCircle, IconEye, IconLoader, IconMarket, IconStore } from "./icons";

type StepState = "complete" | "active" | "pending";

export function AnalysisProgress({ detail }: { detail: StoreDetail }) {
  const run = detail.latest_run;
  if (!run) return null;
  const understanding = stageState(run, ["crawl_agent_run", "ai_classification_agent_run"]);
  const visibility = stageState(run, ["serp_agent_run", "ai_visibility_agent_run"]);
  const market = stageState(run, ["iterative_research_agent_run", "opportunity_recommendation_agent_run"]);

  return (
    <section className="rounded-2xl border border-border bg-surface p-5 shadow-[var(--shadow-soft)] sm:p-6">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold text-text">نكمل تحليل ظهورك الآن</h2>
          <p className="mt-1 text-sm text-text-secondary">ستظهر النتائج هنا بمجرد توفر دليل حقيقي.</p>
        </div>
        <span className="rounded-full bg-primary-tint px-3 py-1 text-xs font-medium text-primary">يتحدث تلقائيًا</span>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <ProgressStep icon={IconStore} state={understanding} title="فهمنا متجرك" description="النشاط والمنتجات والفئات" />
        <ProgressStep icon={IconEye} state={visibility} title="نقيس ظهورك" description="Google ومحركات الذكاء الاصطناعي" />
        <ProgressStep icon={IconMarket} state={market} title="نحلل السوق" description="المنافسون والفرص وخطة التحسين" />
      </div>

      {(detail.visibility_summary || detail.ai_visibility_summary || detail.competitors_found > 0) && (
        <div className="mt-5 border-t border-border pt-5">
          <p className="mb-3 text-sm font-semibold text-text">بدأنا نرى صورتك في السوق</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {detail.visibility_summary && <InsightMetric label="ظهورك في Google" value={`${Math.round(detail.visibility_summary.ranking_coverage * 100)}%`} />}
            {detail.ai_visibility_summary && <InsightMetric label="ظهورك في محركات AI" value={`${Math.round(detail.ai_visibility_summary.mention_rate * 100)}%`} />}
            {detail.competitors_found > 0 && <InsightMetric label="جهات نتابعها في السوق" value={String(detail.competitors_found)} />}
          </div>
        </div>
      )}
    </section>
  );
}

function stageState(run: ResearchRunSummary, agentTypes: string[]): StepState {
  const matching = agentTypes.map((type) => run.agent_runs.find((agent) => agent.agent_type === type));
  if (matching.every((agent) => agent?.status === "completed")) return "complete";
  if (matching.some((agent) => agent?.status === "running" || agent?.status === "completed")) return "active";
  return "pending";
}

function ProgressStep({ icon: Icon, state, title, description }: { icon: React.ComponentType<{ className?: string }>; state: StepState; title: string; description: string }) {
  return (
    <div className={`flex items-start gap-3 rounded-xl border p-3.5 ${state === "active" ? "border-primary/30 bg-primary-tint/50" : "border-border bg-bg-subtle/50"}`}>
      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${state === "complete" ? "bg-success-tint text-success" : state === "active" ? "bg-primary text-on-primary" : "bg-neutral-tint text-text-tertiary"}`}>
        {state === "complete" ? <IconCheckCircle className="h-4.5 w-4.5" /> : state === "active" ? <IconLoader className="h-4.5 w-4.5 animate-spin" /> : <Icon className="h-4.5 w-4.5" />}
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-text">{title}</p>
        <p className="mt-0.5 text-xs leading-5 text-text-secondary">{description}</p>
      </div>
    </div>
  );
}

function InsightMetric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-bg-subtle px-4 py-3"><p className="text-xl font-bold text-text">{value}</p><p className="mt-1 text-xs text-text-secondary">{label}</p></div>;
}
