"use client";

/** Small typed values: durations, timestamps, token counts, cost, ids. All mono, all null-safe. */
import { Check, Copy } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { DASH, formatCost, formatCount, formatDuration, formatRelative, formatUtc, formatUtcTime, shortId } from "@/lib/format";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

const NUMERIC = "num font-mono text-xs";

/** Unknown values are dimmed so a dash never reads as a measurement. */
const dim = (value: unknown) => (value == null ? "text-fg-subtle" : undefined);

export function Duration({ ms, className }: { ms: number | null; className?: string }) {
  return (
    <span className={cn(NUMERIC, dim(ms), className)} title={ms == null ? "Not known yet" : `${formatCount(ms)} ms`}>
      {formatDuration(ms)}
    </span>
  );
}

export function Tokens({ value, className }: { value: number | null; className?: string }) {
  return (
    <span className={cn(NUMERIC, dim(value), className)} title={value == null ? "No token usage was reported" : undefined}>
      {formatCount(value)}
    </span>
  );
}

export function Cost({ usd, className }: { usd: number | null; className?: string }) {
  return (
    <span className={cn(NUMERIC, dim(usd), className)} title={usd == null ? "Unknown: no usage data or no pricing for this model" : `$${usd}`}>
      {formatCost(usd)}
    </span>
  );
}

/**
 * A timestamp. `relative` shows "5m ago" with the exact UTC instant on hover; `utc` and `time`
 * show the stored instant itself.
 */
export function Timestamp({
  value,
  mode = "relative",
  className,
}: {
  value: string | null;
  mode?: "relative" | "utc" | "time";
  className?: string;
}) {
  const now = useNow();
  if (!value) return <span className={cn(NUMERIC, "text-fg-subtle", className)}>{DASH}</span>;
  const text =
    mode === "time" ? formatUtcTime(value) : mode === "utc" || now === null ? formatUtc(value) : formatRelative(value, now);
  return (
    <time dateTime={value} title={formatUtc(value)} className={cn(mode === "relative" ? "whitespace-nowrap" : NUMERIC, className)}>
      {text}
    </time>
  );
}

export function CopyButton({ value, label, className }: { value: string; label: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);
  const Icon = copied ? Check : Copy;
  return (
    <button
      type="button"
      aria-label={copied ? "Copied" : `Copy ${label}`}
      title={copied ? "Copied" : `Copy ${label}`}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void navigator.clipboard.writeText(value).then(() => setCopied(true));
      }}
      className={cn(
        "relative z-10 inline-flex size-5 shrink-0 items-center justify-center rounded-sm text-fg-subtle transition-colors duration-150 ease-out hover:bg-hover hover:text-fg",
        copied && "text-completed",
        className,
      )}
    >
      <Icon className="size-3" aria-hidden="true" />
    </button>
  );
}

/** An id, shortened, in mono. The full id is the tooltip and what the copy button copies. */
export function IdChip({ id, href, full = false, className }: { id: string; href?: string; full?: boolean; className?: string }) {
  const text = full ? id : shortId(id);
  return (
    <span className={cn("group/id inline-flex items-center gap-0.5 font-mono text-xs", className)}>
      {href ? (
        <Link href={href} title={id} className="relative z-10 rounded-sm text-fg underline-offset-2 hover:underline">
          {text}
        </Link>
      ) : (
        <span title={id}>{text}</span>
      )}
      <CopyButton value={id} label="id" className="opacity-0 focus-visible:opacity-100 group-hover/id:opacity-100" />
    </span>
  );
}
