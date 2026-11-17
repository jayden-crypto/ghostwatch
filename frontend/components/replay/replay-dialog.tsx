"use client";

/**
 * Requesting a replay (contract §10): `POST /executions/{execution_id}/replay`.
 *
 * Sandbox is the default. Live runs the agent's tools for real, so it can only be submitted after
 * the authorization box is ticked; the request then carries `authorize_side_effects: true`. If the
 * API still answers `side_effect_authorization_required`, its message is shown as it is.
 */
import { History, ShieldCheck, TriangleAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage, isApiError } from "@/lib/api/errors";
import { useCreateReplay } from "@/lib/api/hooks";
import type { ExecutionSummary, ReplayCreateBody, ReplayMode } from "@/lib/api/types";
import { shortId } from "@/lib/format";
import { AUTHORIZATION_LABEL, LIVE_RULE, SANDBOX_RULE } from "@/lib/replay";
import { cn } from "@/lib/utils";

function ModeOption({
  mode,
  selected,
  onSelect,
  icon,
  title,
  tag,
  children,
}: {
  mode: ReplayMode;
  selected: boolean;
  onSelect: (mode: ReplayMode) => void;
  icon: ReactNode;
  title: string;
  tag?: string;
  children: ReactNode;
}) {
  const descriptionId = useId();
  return (
    <label
      className={cn(
        // `relative` keeps the visually hidden radio inside its card, so focusing it never scrolls the page.
        "relative flex cursor-pointer gap-3 rounded-lg border px-3 py-2.5 transition-colors duration-150 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring/60",
        selected ? (mode === "live" ? "border-timed-out/70 bg-timed-out/[0.06]" : "border-fg/50 bg-raised") : "border-line hover:bg-raised/60",
      )}
    >
      <input
        type="radio"
        name="replay-mode"
        value={mode}
        checked={selected}
        onChange={() => onSelect(mode)}
        aria-describedby={descriptionId}
        className="sr-only"
      />
      <span className={cn("mt-0.5 shrink-0", selected ? (mode === "live" ? "text-timed-out" : "text-fg") : "text-fg-subtle")}>{icon}</span>
      <span className="min-w-0">
        <span className="flex items-center gap-2 text-sm font-medium">
          {title}
          {tag && <span className="rounded-sm border border-line px-1.5 text-[11px] font-normal leading-4 text-fg-muted">{tag}</span>}
        </span>
        <span id={descriptionId} className="mt-0.5 block text-xs text-fg-muted">
          {children}
        </span>
      </span>
    </label>
  );
}

function ReplayForm({ execution, onDone }: { execution: Pick<ExecutionSummary, "id">; onDone: () => void }) {
  const router = useRouter();
  const create = useCreateReplay(execution.id);
  const [mode, setMode] = useState<ReplayMode>("sandbox");
  const [authorized, setAuthorized] = useState(false);
  const [note, setNote] = useState("");
  const authorizationId = useId();
  const noteId = useId();

  const blocked = mode === "live" && !authorized;
  const submit = () => {
    if (blocked || create.isPending) return;
    const body: ReplayCreateBody = { mode };
    if (mode === "live") body.authorize_side_effects = authorized;
    if (note.trim()) body.note = note.trim();
    create.mutate(body, {
      onSuccess: (replay) => {
        onDone();
        router.push(`/replays/${replay.id}`);
      },
    });
  };

  return (
    <form
      className="grid gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <fieldset className="grid gap-2">
        <legend className="mb-2 text-xs font-medium text-fg-muted">Mode</legend>
        <ModeOption mode="sandbox" selected={mode === "sandbox"} onSelect={setMode} icon={<ShieldCheck className="size-4" aria-hidden="true" />} title="Sandbox" tag="default">
          {SANDBOX_RULE}
        </ModeOption>
        <ModeOption
          mode="live"
          selected={mode === "live"}
          onSelect={(next) => {
            setMode(next);
            setAuthorized(false);
          }}
          icon={<TriangleAlert className="size-4" aria-hidden="true" />}
          title="Live"
        >
          {LIVE_RULE}
        </ModeOption>
      </fieldset>

      {mode === "live" && (
        <div className="flex items-start gap-2.5 rounded-lg border border-timed-out/50 px-3 py-2.5">
          <Checkbox id={authorizationId} checked={authorized} onCheckedChange={(next) => setAuthorized(next === true)} className="mt-0.5 border-fg-muted" />
          <label htmlFor={authorizationId} className="cursor-pointer text-sm">
            {AUTHORIZATION_LABEL}
            <span className="mt-0.5 block text-xs text-fg-muted">Required for a live replay. The request is refused without it.</span>
          </label>
        </div>
      )}

      <div className="grid gap-1.5">
        <label htmlFor={noteId} className="text-xs font-medium text-fg-muted">
          Note <span className="font-normal text-fg-subtle">(optional)</span>
        </label>
        <Textarea id={noteId} value={note} onChange={(event) => setNote(event.target.value)} rows={2} placeholder="What changed since the original run?" />
      </div>

      <p className="text-xs text-fg-subtle">
        A replay is run by a replay worker, a process that has the agent&apos;s code. It stays pending until one picks it up.
      </p>

      {create.error && (
        <div role="alert" className="rounded-lg border border-failed/40 px-3 py-2.5">
          <p className="text-sm font-medium">
            {isApiError(create.error) && create.error.code === "side_effect_authorization_required"
              ? "The API refused the live replay: authorization is required"
              : "The replay could not be requested"}
          </p>
          <p className="mt-0.5 text-xs text-fg-muted">{errorMessage(create.error)}</p>
          {isApiError(create.error) && (
            <p className="mt-1 font-mono text-[11px] text-fg-subtle">
              {create.error.code} · HTTP {create.error.status}
            </p>
          )}
        </div>
      )}

      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={blocked || create.isPending} title={blocked ? "Tick the authorization box to request a live replay" : undefined}>
          {create.isPending ? "Requesting…" : mode === "live" ? "Request live replay" : "Request sandbox replay"}
        </Button>
      </DialogFooter>
    </form>
  );
}

/** The trace header's Replay button, with the dialog it opens. */
export function ReplayButton({ execution }: { execution: Pick<ExecutionSummary, "id" | "status"> }) {
  const [open, setOpen] = useState(false);
  if (execution.status === "running") {
    return (
      <Button variant="outline" size="sm" disabled title="This run is still in progress. It can be replayed once it ends.">
        <History aria-hidden="true" />
        Replay
      </Button>
    );
  }
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <History aria-hidden="true" />
          Replay
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Replay this execution</DialogTitle>
          <DialogDescription>
            Re-runs <code className="font-mono text-xs">{shortId(execution.id)}</code> with its recorded input, then compares the result with the original.
          </DialogDescription>
        </DialogHeader>
        {/* Mounted with the dialog, so the form starts from its defaults every time it opens. */}
        <ReplayForm execution={execution} onDone={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  );
}
