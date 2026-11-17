/**
 * A large generated trace, for checking that the trace explorer stays smooth with hundreds of
 * steps. Used by the unit tests and by the mock adapter's `?__state=large` debug override only.
 * It never reaches a live response.
 */
import type { Step, Trace } from "@/lib/api/types";

/** Ids in a range no recorded step uses, so a generated step can never be mistaken for a real one. */
const stepId = (n: number) => `stp_ffff${n.toString(16).padStart(28, "0")}`;

/** `base` with its steps replaced by `count` generated ones: batches of tool and model calls, three levels deep. */
export function withSyntheticSteps(base: Trace, count: number): Trace {
  const start = Date.parse(base.execution.started_at);
  const steps: Step[] = [];
  let cursor = 0;
  const add = (name: string, type: Step["type"], parent: Step | null, duration: number, failed = false): Step => {
    const ordinal = steps.length + 1;
    const step: Step = {
      id: stepId(ordinal),
      execution_id: base.execution.id,
      parent_step_id: parent?.id ?? null,
      ordinal,
      depth: parent ? parent.depth + 1 : 0,
      name,
      type,
      status: failed ? "failed" : "completed",
      started_at: new Date(start + cursor).toISOString(),
      ended_at: new Date(start + cursor + duration).toISOString(),
      duration_ms: duration,
      offset_ms: cursor,
      input: { index: ordinal },
      output: failed ? null : { ok: true },
      error: failed ? { type: "HTTPError", message: "HTTP 503 Service Unavailable", stacktrace: null } : null,
      tool_name: type === "tool_call" ? name : null,
      model: type === "llm_call" ? "demo-llm-1" : null,
      tokens_input: type === "llm_call" ? 120 : null,
      tokens_output: type === "llm_call" ? 40 : null,
      attempt: 1,
      metadata: {},
    };
    steps.push(step);
    return step;
  };

  let batch = 0;
  while (steps.length < count) {
    batch += 1;
    const parent = add(`batch_${batch}`, "reasoning", null, 0);
    const batchStart = cursor;
    for (let item = 1; item <= 4 && steps.length < count; item++) {
      const group = add(`item_${item}`, "custom", parent, 0);
      const groupStart = cursor;
      for (const [name, type, duration] of [["fetch", "tool_call", 40], ["summarize", "llm_call", 90]] as const) {
        if (steps.length >= count) break;
        add(name, type, group, duration + ((steps.length * 7) % 30), steps.length % 97 === 0);
        cursor += duration + 5;
      }
      group.duration_ms = cursor - groupStart;
      group.ended_at = new Date(start + cursor).toISOString();
    }
    parent.duration_ms = cursor - batchStart;
    parent.ended_at = new Date(start + cursor).toISOString();
    cursor += 3;
  }

  return {
    ...base,
    execution: {
      ...base.execution,
      step_count: steps.length,
      duration_ms: cursor,
      ended_at: new Date(start + cursor).toISOString(),
    },
    steps,
  };
}
