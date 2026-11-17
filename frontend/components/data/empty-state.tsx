import { Construction, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** What a view shows when there is nothing to show: what would be here, and how to get it. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  command,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description: ReactNode;
  /** A shell command that produces data for this view. */
  command?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-line px-6 py-14 text-center">
      <Icon className="size-5 text-fg-subtle" strokeWidth={1.5} aria-hidden="true" />
      <div className="max-w-md">
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-1 text-fg-muted">{description}</p>
      </div>
      {command && (
        <code className="rounded-md border border-line-subtle bg-surface px-2.5 py-1.5 font-mono text-xs text-fg-muted">
          {command}
        </code>
      )}
      {action}
    </div>
  );
}

/** For anything that does not exist yet. Says so; never shows sample content in its place. */
export function NotImplemented({ what, issue }: { what: string; issue: string }) {
  return <EmptyState icon={Construction} title="Not implemented" description={`${what} is not built yet (${issue}).`} />;
}
