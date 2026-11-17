/**
 * The one door to data. Every request in the app goes through `api`.
 *
 * This is the only module that knows whether the data is live or mocked. It picks an adapter from
 * NEXT_PUBLIC_API_MODE and loads it on first use, so a live build never downloads the fixtures.
 */
import { API_MODE } from "./config";
import type {
  Agent,
  AgentListParams,
  Anomaly,
  AnomalyListParams,
  AnomalyUpdateBody,
  EventListParams,
  ExecutionDetail,
  ExecutionListParams,
  ExecutionSummary,
  Health,
  ID,
  Investigation,
  InvestigationCreateBody,
  InvestigationListParams,
  Page,
  Replay,
  ReplayCreateBody,
  ReplayListParams,
  StatsOverview,
  StatsTimeseries,
  StatsWindow,
  StoredEvent,
  TimeseriesParams,
  Trace,
} from "./types";

/** One method per contract endpoint the dashboard calls. Both adapters implement exactly this. */
export interface GhostwatchApi {
  /** GET /health */
  health(): Promise<Health>;
  /** GET /agents */
  listAgents(params?: AgentListParams): Promise<Page<Agent>>;
  /** GET /agents/{agent_id} */
  getAgent(agentId: ID): Promise<Agent>;
  /** GET /executions */
  listExecutions(params?: ExecutionListParams): Promise<Page<ExecutionSummary>>;
  /** GET /executions/{execution_id} */
  getExecution(executionId: ID): Promise<ExecutionDetail>;
  /** GET /executions/{execution_id}/trace */
  getTrace(executionId: ID): Promise<Trace>;
  /** GET /executions/{execution_id}/events */
  listEvents(executionId: ID, params?: EventListParams): Promise<Page<StoredEvent>>;
  /** GET /stats/overview */
  statsOverview(window?: StatsWindow): Promise<StatsOverview>;
  /** GET /stats/timeseries */
  statsTimeseries(params?: TimeseriesParams): Promise<StatsTimeseries>;
  /** GET /anomalies */
  listAnomalies(params?: AnomalyListParams): Promise<Page<Anomaly>>;
  /** GET /anomalies/{anomaly_id} */
  getAnomaly(anomalyId: ID): Promise<Anomaly>;
  /** PATCH /anomalies/{anomaly_id} */
  updateAnomaly(anomalyId: ID, body: AnomalyUpdateBody): Promise<Anomaly>;
  /** GET /investigations */
  listInvestigations(params?: InvestigationListParams): Promise<Page<Investigation>>;
  /** GET /investigations/{execution_id}. Rejects with `not_found` when none exists yet. */
  getInvestigation(executionId: ID): Promise<Investigation>;
  /** POST /investigations/{execution_id} */
  createInvestigation(executionId: ID, body?: InvestigationCreateBody): Promise<Investigation>;
  /** GET /replays */
  listReplays(params?: ReplayListParams): Promise<Page<Replay>>;
  /** GET /replays/{replay_id} */
  getReplay(replayId: ID): Promise<Replay>;
  /** POST /executions/{execution_id}/replay */
  createReplay(executionId: ID, body: ReplayCreateBody): Promise<Replay>;
}

let adapter: Promise<GhostwatchApi> | undefined;

function loadAdapter(): Promise<GhostwatchApi> {
  adapter ??=
    API_MODE === "live"
      ? import("./live").then((module) => module.liveApi)
      : import("./mock").then((module) => module.mockApi);
  return adapter;
}

type Method = keyof GhostwatchApi;

export const api = new Proxy({} as GhostwatchApi, {
  get:
    (_target, method: Method) =>
    async (...args: unknown[]) => {
      const implementation = (await loadAdapter())[method] as (...args: unknown[]) => Promise<unknown>;
      return implementation(...args);
    },
});
