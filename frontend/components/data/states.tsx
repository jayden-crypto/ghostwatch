/** Error and loading states shared by every data view. */
import { CircleAlert, RotateCw } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage, isApiError } from "@/lib/api/errors";
import { TONE_TEXT, type Tone } from "@/lib/enums";
import { cn } from "@/lib/utils";

/**
 * A failed request: the API's own message, its error code, and a way to try again.
 * The message is shown as received; nothing here guesses at a cause.
 */
export function ErrorState({
  error,
  onRetry,
  title = "This could not be loaded",
  className,
  compact = false,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
  /** For panels inside a page: less padding, no border. */
  compact?: boolean;
}) {
  const code = isApiError(error) ? error.code : null;
  const status = isApiError(error) ? error.status : null;
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center gap-3 text-center",
        compact ? "px-4 py-8" : "rounded-lg border border-failed/30 px-6 py-12",
        className,
      )}
    >
      <CircleAlert className="size-5 text-failed" strokeWidth={1.5} aria-hidden="true" />
      <div className="max-w-lg">
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-1 text-fg-muted">{errorMessage(error)}</p>
        {code && (
          <p className="mt-2 font-mono text-xs text-fg-subtle">
            {code}
            {status !== null && ` · HTTP ${status}`}
          </p>
        )}
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RotateCw aria-hidden="true" />
          Retry
        </Button>
      )}
    </div>
  );
}

/** A quiet marker that data on screen is being refreshed. */
export function Refreshing({ active }: { active: boolean }) {
  return (
    <span aria-live="polite" className={cn("text-xs text-fg-subtle transition-opacity duration-150", active ? "opacity-100" : "opacity-0")}>
      {active ? "Updating…" : ""}
    </span>
  );
}

/** A titled panel: the unit the overview and detail pages are built from. */
export function Panel({
  title,
  action,
  children,
  className,
  flush = false,
}: {
  title: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Content runs to the panel's edges (tables). */
  flush?: boolean;
}) {
  return (
    <section className={cn("flex min-w-0 flex-col rounded-lg border border-line-subtle bg-surface", className)}>
      <header className="flex h-10 shrink-0 items-center justify-between gap-3 border-b border-line-subtle px-4">
        <h2 className="truncate text-13 font-medium">{title}</h2>
        {action && <div className="flex shrink-0 items-center gap-2 text-fg-muted">{action}</div>}
      </header>
      <div className={cn("min-w-0 flex-1", !flush && "p-4")}>{children}</div>
    </section>
  );
}

/** One number with its label. `value` is already formatted; unknown is a dash, never 0. */
export function StatTile({
  label,
  value,
  detail,
  tone,
  className,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  /** Colours the number when it means something (failures, open anomalies). Omit for neutral. */
  tone?: Tone;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1 rounded-lg border border-line-subtle bg-surface px-4 py-3", className)}>
      <span className="truncate text-xs text-fg-muted">{label}</span>
      <span className={cn("num truncate font-mono text-xl font-medium tracking-tight", tone && TONE_TEXT[tone])}>{value}</span>
      {detail && <span className="truncate text-xs text-fg-subtle">{detail}</span>}
    </div>
  );
}

export function StatTileSkeleton() {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line-subtle bg-surface px-4 py-3">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-6 w-16" />
      <Skeleton className="h-3 w-24" />
    </div>
  );
}
