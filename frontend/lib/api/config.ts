/**
 * Where data comes from. Read once from the environment at build time.
 * Only lib/api/client.ts, the header badge and the /settings route (which reports it) may look at
 * the mode: components never do.
 */
export type ApiMode = "mock" | "live";

/** Anything other than "live" means mock, so a missing variable can never show fixtures unlabelled as real data. */
export const API_MODE: ApiMode = process.env.NEXT_PUBLIC_API_MODE === "live" ? "live" : "mock";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");
