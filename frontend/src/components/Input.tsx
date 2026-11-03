import { forwardRef } from "react";
import type { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string;
  label: string;
  error?: string;
  hint?: string;
}

const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { id, label, error, hint, ...rest },
  ref,
) {
  const hintId = hint !== undefined && hint !== "" ? `${id}-hint` : undefined;
  const errorId = error !== undefined && error !== "" ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div>
      <label htmlFor={id} className="mb-1 block font-semibold">
        {label}
      </label>
      <input
        id={id}
        ref={ref}
        aria-invalid={errorId !== undefined || undefined}
        aria-describedby={describedBy}
        className="min-h-[44px] w-full rounded-md border border-line bg-surface px-3 text-ink transition-colors duration-150 placeholder:text-muted/70 hover:border-muted"
        {...rest}
      />
      {hintId !== undefined && (
        <p id={hintId} className="mt-1 text-sm text-muted">
          {hint}
        </p>
      )}
      {errorId !== undefined && (
        <p id={errorId} role="alert" className="mt-1 text-sm font-semibold text-sev-high">
          {error}
        </p>
      )}
    </div>
  );
});

export default Input;
