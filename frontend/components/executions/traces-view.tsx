"use client";

/** /traces: open a trace by execution id, or pick one of the most recent runs. */
import { ArrowRight, Inbox } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { EmptyState } from "@/components/data/empty-state";
import { ErrorState, Panel } from "@/components/data/states";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";
import { LIST_POLL_MS, useExecutions } from "@/lib/api/hooks";

import { ExecutionsTable } from "./executions-table";

const EXECUTION_ID = /^exe_[0-9a-f]{32}$/;
const RECENT = 15;

export function TracesView() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const recent = useExecutions({ limit: RECENT }, { refetchInterval: LIST_POLL_MS });

  const open = (event: FormEvent) => {
    event.preventDefault();
    const id = value.trim();
    if (!EXECUTION_ID.test(id)) {
      setProblem("An execution id is exe_ followed by 32 hexadecimal characters.");
      return;
    }
    router.push(`/executions/${id}`);
  };

  return (
    <Page title="Traces" description="The step-by-step record of an execution: what ran, in what order, for how long, with what input and output.">
      <form onSubmit={open} className="flex max-w-2xl flex-col gap-1.5" noValidate>
        <label htmlFor="trace-id" className="text-xs text-fg-muted">
          Open a trace by execution id
        </label>
        <div className="flex gap-2">
          <input
            id="trace-id"
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
              setProblem(null);
            }}
            placeholder="exe_3f9c2a7e1b4d4e0f9a8b7c6d5e4f3a2b"
            spellCheck={false}
            autoComplete="off"
            aria-invalid={problem !== null}
            aria-describedby={problem ? "trace-id-problem" : undefined}
            className="h-8 min-w-0 flex-1 rounded-md border border-line bg-surface px-2.5 font-mono text-xs outline-none transition-colors duration-150 placeholder:text-fg-subtle hover:border-fg-subtle/50 focus-visible:border-ring aria-invalid:border-failed"
          />
          <Button type="submit" variant="outline">
            Open trace
            <ArrowRight aria-hidden="true" />
          </Button>
        </div>
        {problem && (
          <p id="trace-id-problem" role="alert" className="text-xs text-failed">
            {problem}
          </p>
        )}
      </form>

      <Panel
        title="Recent traces"
        flush
        action={
          <Link href="/executions" className="rounded-sm text-xs underline-offset-2 hover:text-fg hover:underline">
            All executions
          </Link>
        }
      >
        {recent.error ? (
          <ErrorState error={recent.error} onRetry={() => void recent.refetch()} title="Recent traces could not be loaded" compact />
        ) : (
          <ExecutionsTable
            rows={recent.data?.items}
            skeletonRows={8}
            caption="Recent traces"
            empty={
              <div className="p-6">
                <EmptyState
                  icon={Inbox}
                  title="No traces yet"
                  description="A trace is recorded for every execution an instrumented agent reports. To create sample history:"
                  command="cd demo && uv run python seed.py"
                />
              </div>
            }
          />
        )}
      </Panel>
    </Page>
  );
}
