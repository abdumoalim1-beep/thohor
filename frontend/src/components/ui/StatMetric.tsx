import { IconTrendDown, IconTrendUp } from "./icons";

type StatMetricProps = {
  label: string;
  value: string;
  hint?: string;
  trend?: "up" | "down" | "flat";
  trendLabel?: string;
};

export function StatMetric({ label, value, hint, trend, trendLabel }: StatMetricProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm text-text-secondary">{label}</span>
      <div className="flex items-baseline gap-2">
        <span className="tabular text-2xl font-semibold text-text">{value}</span>
        {trend && trend !== "flat" && (
          <span
            className={`inline-flex items-center gap-0.5 text-xs font-medium ${
              trend === "up" ? "text-success" : "text-danger"
            }`}
          >
            {trend === "up" ? <IconTrendUp className="h-3.5 w-3.5" /> : <IconTrendDown className="h-3.5 w-3.5" />}
            {trendLabel}
          </span>
        )}
      </div>
      {hint && <span className="text-xs text-text-tertiary">{hint}</span>}
    </div>
  );
}
