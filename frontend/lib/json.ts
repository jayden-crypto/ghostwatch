import type { Json, TruncatedPayload } from "@/lib/api/types";

export const isJsonObject = (value: Json): value is { [k: string]: Json } =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Contract §0: what a payload field larger than 64 KB is stored as. */
export const isTruncatedPayload = (value: Json): value is Json & TruncatedPayload =>
  isJsonObject(value) && value._truncated === true && typeof value.original_bytes === "number" && typeof value.preview === "string";
