import { REPLAY_SOURCES, type Json, type ReplaySource, type Step, type TruncatedPayload } from "@/lib/api/types";

export const isJsonObject = (value: Json): value is { [k: string]: Json } =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Contract §0: what a payload field larger than 64 KB is stored as. */
export const isTruncatedPayload = (value: Json): value is Json & TruncatedPayload =>
  isJsonObject(value) && value._truncated === true && typeof value.original_bytes === "number" && typeof value.preview === "string";

/**
 * Contract §10: `metadata.replay_source` of a step of a replay execution, or null for a step of an
 * ordinary run (or a value this version of the contract does not define).
 */
export function replaySourceOf(step: Pick<Step, "metadata">): ReplaySource | null {
  const source = step.metadata.replay_source;
  return typeof source === "string" && (REPLAY_SOURCES as readonly string[]).includes(source) ? (source as ReplaySource) : null;
}
