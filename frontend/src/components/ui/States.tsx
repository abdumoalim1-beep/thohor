import { ReactNode } from "react";

import { IconAlertTriangle, IconInfoCircle, IconLoader } from "./icons";

export function LoadingState({ label = "جارٍ التحميل..." }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-text-secondary">
      <IconLoader className="h-4 w-4 animate-spin text-primary" />
      {label}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-danger/20 bg-danger-tint px-4 py-3 text-sm text-danger">
      <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

/** Section 13 — explicit "we don't know" states, never a silent zero when a
 * metric simply wasn't measured. */
export function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border-strong bg-bg-subtle px-6 py-10 text-center">
      <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-full bg-neutral-tint text-text-tertiary">
        {icon ?? <IconInfoCircle className="h-5 w-5" />}
      </div>
      <p className="text-sm font-medium text-text">{title}</p>
      {description && <p className="max-w-sm text-sm text-text-secondary">{description}</p>}
      {action}
    </div>
  );
}

/** A metric that exists as a concept but genuinely has no data behind it
 * yet — never rendered as "0%", always this explicit inline note instead
 * (Section 13/16: "لا تساوي بين 'لم نقسه' و'نتيجته صفر'"). */
export function NotMeasuredYet({ label = "لم نقِس هذا بعد" }: { label?: string }) {
  return <span className="text-sm text-text-tertiary">{label}</span>;
}
