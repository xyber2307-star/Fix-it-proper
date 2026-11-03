import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

export type AlertTone = "info" | "warning" | "error" | "success";

interface AlertProps {
  tone: AlertTone;
  title: string;
  children?: ReactNode;
}

const TONE_CLASSES: Record<AlertTone, string> = {
  info: "border-accent/30 bg-accent-soft text-ink",
  warning: "border-sev-medium/30 bg-sev-medium-soft text-ink",
  error: "border-sev-high/30 bg-sev-high-soft text-ink",
  success: "border-accent/30 bg-accent-soft text-ink",
};

const TONE_ICONS = {
  info: Info,
  warning: TriangleAlert,
  error: CircleAlert,
  success: CircleCheck,
} as const;

export default function Alert({ tone, title, children }: AlertProps) {
  const Icon = TONE_ICONS[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`flex gap-3 rounded-md border p-4 ${TONE_CLASSES[tone]}`}
    >
      <Icon className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <div>
        <p className="font-semibold">{title}</p>
        {children !== undefined && <div className="mt-1 text-sm">{children}</div>}
      </div>
    </div>
  );
}
