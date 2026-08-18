import { HTMLAttributes } from "react";

export type BadgeVariant = "primary" | "success" | "warning" | "danger" | "info" | "neutral";

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: BadgeVariant;
  dot?: boolean;
};

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  primary: "bg-primary-tint text-primary-hover",
  success: "bg-success-tint text-success",
  warning: "bg-warning-tint text-warning",
  danger: "bg-danger-tint text-danger",
  info: "bg-info-tint text-info",
  neutral: "bg-neutral-tint text-text-secondary",
};

const DOT_CLASSES: Record<BadgeVariant, string> = {
  primary: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
  neutral: "bg-text-tertiary",
};

export function Badge({ variant = "neutral", dot = false, className = "", children, ...rest }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${VARIANT_CLASSES[variant]} ${className}`}
      {...rest}
    >
      {dot && <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT_CLASSES[variant]}`} />}
      {children}
    </span>
  );
}
