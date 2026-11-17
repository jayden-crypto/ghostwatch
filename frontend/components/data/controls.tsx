"use client";

/** Small filter controls shared by the list pages. All of them are driven by, and write to, the URL. */
import { Search } from "lucide-react";
import { useEffect, useState } from "react";

import { STATS_WINDOWS, type StatsWindow } from "@/lib/api/types";
import { TONE_BG, type Tone } from "@/lib/enums";
import { cn } from "@/lib/utils";

/** The look of every compact control in a filter bar. */
export const CONTROL =
  "h-7 rounded-md border border-line bg-surface px-2 text-13 outline-none transition-colors duration-150 placeholder:text-fg-subtle hover:border-fg-subtle/50 focus-visible:border-ring";

/** A text or number field that reports its value a moment after typing stops. */
export function DebouncedInput({
  value,
  onCommit,
  className,
  ...props
}: Omit<React.ComponentProps<"input">, "value" | "onChange"> & { value: string; onCommit: (value: string) => void }) {
  const [draft, setDraft] = useState(value);
  // The URL can change underneath (back button, Clear): the field follows it.
  const [seen, setSeen] = useState(value);
  if (value !== seen) {
    setSeen(value);
    setDraft(value);
  }
  useEffect(() => {
    if (draft === value) return;
    const timer = setTimeout(() => onCommit(draft), 250);
    return () => clearTimeout(timer);
  }, [draft, value, onCommit]);
  return <input {...props} value={draft} onChange={(event) => setDraft(event.target.value)} className={cn(CONTROL, className)} />;
}

export function SearchInput({ value, onCommit, label, placeholder, className }: { value: string; onCommit: (value: string) => void; label: string; placeholder: string; className?: string }) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" aria-hidden="true" />
      <DebouncedInput type="search" aria-label={label} placeholder={placeholder} value={value} onCommit={onCommit} className={cn("w-64 pl-7", className)} />
    </div>
  );
}

/** A row of toggle chips for choosing any number of values of an enum. */
export function ChipFilter<T extends string>({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: readonly { value: T; label: string; tone: Tone }[];
  selected: readonly T[];
  onChange: (selected: T[]) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1">
      {options.map((option) => {
        const on = selected.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={on}
            // Keeps the options' own order whatever order they were clicked in.
            onClick={() => onChange(options.map((o) => o.value).filter((value) => (value === option.value ? !on : selected.includes(value))))}
            className={cn(CONTROL, "flex items-center gap-1.5 text-fg-muted", on && "border-fg-muted bg-raised text-fg")}
          >
            <span aria-hidden="true" className={cn("size-1.5 rounded-full", TONE_BG[option.tone])} />
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** 24h / 7d / 30d, the windows of `/stats/*`. */
export function WindowSwitch({ value, onChange }: { value: StatsWindow; onChange: (window: StatsWindow) => void }) {
  return (
    <div role="group" aria-label="Time window" className="flex rounded-md border border-line p-0.5">
      {STATS_WINDOWS.map((window) => (
        <button
          key={window}
          type="button"
          aria-pressed={window === value}
          onClick={() => onChange(window)}
          className={cn(
            "h-6 rounded-[5px] px-2.5 font-mono text-xs text-fg-muted transition-colors duration-150 hover:text-fg",
            window === value && "bg-raised text-fg",
          )}
        >
          {window}
        </button>
      ))}
    </div>
  );
}

export const WINDOW_LABEL: Record<StatsWindow, string> = { "24h": "24 hours", "7d": "7 days", "30d": "30 days" };

/** The stats window named in the query string, or the default (7d). */
export const windowFrom = (params: URLSearchParams): StatsWindow => {
  const requested = params.get("window");
  return (STATS_WINDOWS as readonly string[]).includes(requested ?? "") ? (requested as StatsWindow) : "7d";
};
