import { LoaderCircle } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
  children: ReactNode;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "bg-accent text-white hover:bg-accent-strong",
  secondary: "border border-line bg-surface text-ink hover:border-muted",
};

export default function Button({
  variant = "primary",
  loading = false,
  disabled,
  children,
  type,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled === true || loading;
  return (
    <button
      type={type ?? "button"}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={`inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md px-5 font-semibold transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-60 ${VARIANT_CLASSES[variant]}`}
      {...rest}
    >
      {loading && <LoaderCircle className="size-4 motion-safe:animate-spin" aria-hidden="true" />}
      {children}
    </button>
  );
}
