import { ChevronRight } from "lucide-react";

export interface Crumb {
  label: string;
  href?: string;
}

export default function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-muted">
        {items.map((item, index) => {
          const last = index === items.length - 1;
          return (
            <li key={item.label} className="flex items-center gap-1">
              {index > 0 && <ChevronRight className="size-4" aria-hidden="true" />}
              {last || item.href === undefined ? (
                <span aria-current={last ? "page" : undefined} className="text-ink">
                  {item.label}
                </span>
              ) : (
                <a href={item.href} className="underline decoration-line underline-offset-4">
                  {item.label}
                </a>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
