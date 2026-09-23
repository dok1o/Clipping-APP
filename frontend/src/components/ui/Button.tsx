// Button: variants, sizes, loading/disabled states, visible focus ring.
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-blue-600 text-white border-blue-600 hover:bg-blue-700 hover:border-blue-700 disabled:bg-blue-300 disabled:border-blue-300",
  secondary:
    "bg-white text-neutral-700 border-neutral-300 hover:bg-neutral-50 hover:text-neutral-900 disabled:text-neutral-500",
  danger:
    "bg-white text-red-700 border-red-300 hover:bg-red-50 disabled:text-red-300",
  ghost:
    "bg-transparent text-neutral-600 border-transparent hover:bg-neutral-100 hover:text-neutral-900 disabled:text-neutral-500",
};

const SIZES: Record<Size, string> = {
  sm: "px-2 py-1 text-xs gap-1",
  md: "px-3 py-1.5 text-sm gap-1.5",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  children,
  className = "",
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center rounded-md border font-medium motion-safe:transition-colors
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
        disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <span
          className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none"
          aria-hidden="true"
        />
      ) : (
        icon
      )}
      {children}
    </button>
  );
}
