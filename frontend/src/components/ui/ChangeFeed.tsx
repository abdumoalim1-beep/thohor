import Link from "next/link";

import { AlertItem } from "@/lib/api";
import { IconAlertTriangle, IconCheckCircle, IconInfoCircle, IconTrendDown } from "./icons";

const SEVERITY_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  critical: IconAlertTriangle,
  warning: IconTrendDown,
  success: IconCheckCircle,
  info: IconInfoCircle,
};

const SEVERITY_CLASSES: Record<string, string> = {
  critical: "text-danger bg-danger-tint",
  warning: "text-warning bg-warning-tint",
  success: "text-success bg-success-tint",
  info: "text-info bg-info-tint",
};

/** Section 12/6 — "آخر التغيرات" real timeline built from app.alerts (has
 * real created_at + typed events like ai-visibility-dropped/
 * recommendation-showing-results), used instead of a fabricated historical
 * trend chart the API doesn't support. One component, three former
 * independent renderings (Overview top-5, Overview full timeline, Alerts
 * page) collapse into this with a `variant` prop. */
export function ChangeFeed({
  alerts,
  variant = "list",
  limit,
  storeId,
  onMarkRead,
}: {
  alerts: AlertItem[];
  variant?: "list" | "timeline";
  limit?: number;
  storeId?: string;
  onMarkRead?: (id: string) => void;
}) {
  const sorted = [...alerts].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  const shown = limit ? sorted.slice(0, limit) : sorted;

  if (shown.length === 0) return null;

  if (variant === "timeline") {
    return (
      <ul className="flex flex-col gap-3 border-e-2 border-border pe-4">
        {shown.map((e) => (
          <li key={e.id} className="relative text-sm">
            <span className="absolute -end-[1.4rem] top-1.5 h-2 w-2 rounded-full bg-text-tertiary" />
            <p className="text-xs text-text-tertiary">{new Date(e.created_at).toLocaleDateString("ar")}</p>
            <p className="text-text-secondary">{e.title}</p>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {shown.map((a) => {
        const Icon = SEVERITY_ICON[a.severity] ?? IconInfoCircle;
        const content = (
          <div className="flex items-start gap-3">
            <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${SEVERITY_CLASSES[a.severity] ?? "bg-neutral-tint text-text-secondary"}`}>
              <Icon className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className={`text-sm ${a.status === "unread" ? "font-semibold text-text" : "text-text-secondary"}`}>{a.title}</p>
              <p className="mt-0.5 text-sm text-text-secondary">{a.message}</p>
            </div>
            {onMarkRead && a.status === "unread" && (
              <button
                type="button"
                onClick={(ev) => {
                  ev.preventDefault();
                  onMarkRead(a.id);
                }}
                className="shrink-0 rounded-md border border-border-strong px-2.5 py-1 text-xs text-text-secondary hover:bg-surface-hover"
              >
                تمّت القراءة
              </button>
            )}
          </div>
        );
        return (
          <li key={a.id} className="rounded-lg border border-border bg-surface p-3.5 shadow-[var(--shadow-soft)]">
            {a.related_recommendation_id && storeId ? (
              <Link href={`/stores/${storeId}/recommendations/${a.related_recommendation_id}`}>{content}</Link>
            ) : (
              content
            )}
          </li>
        );
      })}
    </ul>
  );
}
