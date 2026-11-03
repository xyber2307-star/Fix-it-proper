import { useRef } from "react";
import type { KeyboardEvent, ReactNode } from "react";

export interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
}

interface TabsProps {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
  idPrefix: string;
}

export default function Tabs({ tabs, active, onChange, idPrefix }: TabsProps) {
  const buttons = useRef(new Map<string, HTMLButtonElement>());

  function focusTab(id: string) {
    buttons.current.get(id)?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = tabs.findIndex((tab) => tab.id === active);
    if (index < 0) return;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const direction = event.key === "ArrowRight" ? 1 : -1;
      const next = tabs[(index + direction + tabs.length) % tabs.length];
      onChange(next.id);
      focusTab(next.id);
    } else if (event.key === "Home") {
      event.preventDefault();
      onChange(tabs[0].id);
      focusTab(tabs[0].id);
    } else if (event.key === "End") {
      event.preventDefault();
      onChange(tabs[tabs.length - 1].id);
      focusTab(tabs[tabs.length - 1].id);
    }
  }

  const current = tabs.find((tab) => tab.id === active) ?? tabs[0];

  return (
    <div>
      <div
        role="tablist"
        aria-label="Report sections"
        onKeyDown={onKeyDown}
        className="flex gap-1 border-b border-line"
      >
        {tabs.map((tab) => {
          const selected = tab.id === current.id;
          return (
            <button
              key={tab.id}
              ref={(node) => {
                if (node !== null) buttons.current.set(tab.id, node);
              }}
              role="tab"
              id={`${idPrefix}-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${idPrefix}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.id)}
              className={`min-h-[44px] border-b-2 px-4 font-semibold transition-colors duration-150 ${
                selected
                  ? "border-accent text-ink"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`${idPrefix}-panel-${current.id}`}
        aria-labelledby={`${idPrefix}-tab-${current.id}`}
        tabIndex={0}
        className="pt-6"
      >
        {current.content}
      </div>
    </div>
  );
}
