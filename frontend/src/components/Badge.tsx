import type { Severity } from "../types/api";

const SEVERITY_CLASSES: Record<Severity, string> = {
  high: "bg-sev-high-soft text-sev-high",
  medium: "bg-sev-medium-soft text-sev-medium",
  low: "bg-sev-low-soft text-sev-low",
};

const SEVERITY_LABELS: Record<Severity, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

export default function Badge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-block rounded-sm px-2 py-0.5 text-xs font-semibold ${SEVERITY_CLASSES[severity]}`}
    >
      {SEVERITY_LABELS[severity]}
    </span>
  );
}
