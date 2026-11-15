/**
 * Which type in lib/api/types.ts each fixture file must match.
 *
 * Fixtures are named `<resource>.<operation>[.<variant>].json`; the pair picks the type and the
 * variant is free text. These are the same pairs as `backend/tests/fixture_map.py`.
 */
const TYPES: Record<string, string> = {
  "agents.list": "Page<T.Agent>",
  "agents.get": "Agent",
  "agents.create": "Agent",
  "executions.list": "Page<T.ExecutionSummary>",
  "executions.get": "ExecutionDetail",
  "executions.create": "ExecutionDetail",
  "executions.trace": "Trace",
  "executions.events": "Page<T.StoredEvent>",
  "executions.ingest": "IngestResponse",
  "executions.replay": "Replay",
  "events.list": "Page<T.StoredEvent>",
  "events.ingest": "IngestResponse",
  "stats.overview": "StatsOverview",
  "stats.timeseries": "StatsTimeseries",
  "anomalies.list": "Page<T.Anomaly>",
  "anomalies.get": "Anomaly",
  "anomalies.update": "Anomaly",
  "investigations.list": "Page<T.Investigation>",
  "investigations.get": "Investigation",
  "investigations.create": "Investigation",
  "replays.list": "Page<T.Replay>",
  "replays.get": "Replay",
  "replays.create": "Replay",
  "replays.claim": "ReplayClaim",
  "health.get": "Health",
};

/** The type name (to be prefixed with `T.`) for a fixture file, or null when nothing is mapped. */
export function typeFor(file: string): string | null {
  const parts = file.replace(/\.json$/, "").split(".");
  if (parts[0] === "error") return "ErrorEnvelope";
  return TYPES[`${parts[0]}.${parts[1]}`] ?? null;
}
