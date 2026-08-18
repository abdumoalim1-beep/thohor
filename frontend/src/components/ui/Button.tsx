import Link from "next/link";
import { AnchorHTMLAttributes, ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-primary text-on-primary hover:bg-primary-hover shadow-[var(--shadow-soft)]",
  secondary: "bg-surface border border-border-strong text-text hover:bg-surface-hover",
  ghost: "text-text-secondary hover:bg-surface-hover hover:text-text",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
};

const BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-40 disabled:pointer-events-none";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size };

export function Button({ variant = "primary", size = "md", className = "", ...rest }: ButtonProps) {
  return <button className={`${BASE} ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`} {...rest} />;
}

type LinkButtonProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string;
  variant?: Variant;
  size?: Size;
};

export function LinkButton({ href, variant = "primary", size = "md", className = "", ...rest }: LinkButtonProps) {
  return <Link href={href} className={`${BASE} ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`} {...rest} />;
}
