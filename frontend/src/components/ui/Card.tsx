import { HTMLAttributes } from "react";

type CardProps = HTMLAttributes<HTMLDivElement> & {
  padding?: "none" | "sm" | "md" | "lg";
  interactive?: boolean;
};

const PADDING: Record<NonNullable<CardProps["padding"]>, string> = {
  none: "",
  sm: "p-3",
  md: "p-4 sm:p-5",
  lg: "p-6 sm:p-7",
};

export function Card({ padding = "md", interactive = false, className = "", ...rest }: CardProps) {
  return (
    <div
      className={`rounded-lg border border-border bg-surface shadow-[var(--shadow-card)] ${PADDING[padding]} ${
        interactive ? "transition-colors hover:bg-surface-hover cursor-pointer" : ""
      } ${className}`}
      {...rest}
    />
  );
}
