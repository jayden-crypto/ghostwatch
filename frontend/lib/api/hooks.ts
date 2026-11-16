"use client";

/**
 * TanStack Query hooks, one per endpoint. Components use these and never call `api` directly, so
 * cache keys and polling rules live in one place.
 *
 * Polling (kickoff decisions): a trace refetches every 3 s while its execution is running; an
 * investigation every 2 s while queued or running; a replay every 2 s until completed or failed.
 * Polling stops by itself when the status is terminal.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { isNotFound } from "./errors";
import type {
  AgentListParams,
  AnomalyListParams,
  AnomalyStatus,
  EventListParams,
  ExecutionListParams,
  ID,
  Investigation,
  InvestigationCreateBody,
  InvestigationListParams,
  Replay,
  ReplayCreateBody,
  ReplayListParams,
  StatsWindow,
  TimeseriesParams,
} from "./types";

/** Lists that show what agents are doing right now refresh at this interval. */
export const LIST_POLL_MS = 5_000;
export const TRACE_POLL_MS = 3_000;
export const INVESTIGATION_POLL_MS = 2_000;
export const REPLAY_POLL_MS = 2_000;

export const keys = {
  health: ["health"] as const,
  agents: (params: AgentListParams = {}) => ["agents", "list", params] as const,
  agent: (id: ID) => ["agents", "detail", id] as const,
  executions: (params: ExecutionListParams = {}) => ["executions", "list", params] as const,
  execution: (id: ID) => ["executions", "detail", id] as const,
  trace: (id: ID) => ["executions", "trace", id] as const,
  events: (id: ID, params: EventListParams = {}) => ["executions", "events", id, params] as const,
  statsOverview: (window: StatsWindow) => ["stats", "overview", window] as const,
  statsTimeseries: (params: TimeseriesParams = {}) => ["stats", "timeseries", params] as const,
  anomalies: (params: AnomalyListParams = {}) => ["anomalies", "list", params] as const,
  anomaly: (id: ID) => ["anomalies", "detail", id] as const,
  investigations: (params: InvestigationListParams = {}) => ["investigations", "list", params] as const,
  investigation: (executionId: ID) => ["investigations", "detail", executionId] as const,
  replays: (params: ReplayListParams = {}) => ["replays", "list", params] as const,
  replay: (id: ID) => ["replays", "detail", id] as const,
};

export const isInvestigationActive = (investigation: Investigation | null | undefined): boolean =>
  investigation?.status === "queued" || investigation?.status === "running";

export const useHealth = () => useQuery({ queryKey: keys.health, queryFn: () => api.health() });

/** `refetchInterval` keeps a view current while agents run; pass LIST_POLL_MS. */
interface Live {
  refetchInterval?: number;
}

export const useAgents = (params: AgentListParams = {}, live: Live = {}) =>
  useQuery({ queryKey: keys.agents(params), queryFn: () => api.listAgents(params), placeholderData: keepPreviousData, ...live });

export const useAgent = (id: ID) => useQuery({ queryKey: keys.agent(id), queryFn: () => api.getAgent(id) });

/** `placeholderData` keeps the previous page on screen while a filter or page change loads. */
export const useExecutions = (params: ExecutionListParams = {}, options: { enabled?: boolean; refetchInterval?: number } = {}) =>
  useQuery({
    queryKey: keys.executions(params),
    queryFn: () => api.listExecutions(params),
    placeholderData: keepPreviousData,
    enabled: options.enabled,
    refetchInterval: options.refetchInterval,
  });

export const useExecution = (id: ID) => useQuery({ queryKey: keys.execution(id), queryFn: () => api.getExecution(id) });

export const useTrace = (executionId: ID) =>
  useQuery({
    queryKey: keys.trace(executionId),
    queryFn: () => api.getTrace(executionId),
    refetchInterval: (query) => (query.state.data?.execution.status === "running" ? TRACE_POLL_MS : false),
  });

export const useEvents = (executionId: ID, params: EventListParams = {}, options: { enabled?: boolean } = {}) =>
  useQuery({
    queryKey: keys.events(executionId, params),
    queryFn: () => api.listEvents(executionId, params),
    placeholderData: keepPreviousData,
    enabled: options.enabled,
  });

export const useStatsOverview = (window: StatsWindow, live: Live = {}) =>
  useQuery({ queryKey: keys.statsOverview(window), queryFn: () => api.statsOverview(window), placeholderData: keepPreviousData, ...live });

export const useStatsTimeseries = (params: TimeseriesParams = {}, live: Live = {}) =>
  useQuery({
    queryKey: keys.statsTimeseries(params),
    queryFn: () => api.statsTimeseries(params),
    placeholderData: keepPreviousData,
    ...live,
  });

export const useAnomalies = (params: AnomalyListParams = {}, live: Live = {}) =>
  useQuery({ queryKey: keys.anomalies(params), queryFn: () => api.listAnomalies(params), placeholderData: keepPreviousData, ...live });

/** One anomaly by id. Disabled while `id` is null. */
export const useAnomaly = (id: ID | null) =>
  useQuery({ queryKey: keys.anomaly(id ?? ""), queryFn: () => api.getAnomaly(id!), enabled: id !== null });

export const useInvestigations = (params: InvestigationListParams = {}, live: Live = {}) =>
  useQuery({
    queryKey: keys.investigations(params),
    queryFn: () => api.listInvestigations(params),
    placeholderData: keepPreviousData,
    ...live,
  });

/**
 * The latest investigation of an execution. `data` is `null` when none exists yet: the contract's
 * 404 here is a normal state ("not investigated"), not an error.
 */
export const useInvestigation = (executionId: ID, options: { enabled?: boolean } = {}) =>
  useQuery({
    queryKey: keys.investigation(executionId),
    queryFn: async (): Promise<Investigation | null> => {
      try {
        return await api.getInvestigation(executionId);
      } catch (error) {
        if (isNotFound(error)) return null;
        throw error;
      }
    },
    refetchInterval: (query) => (isInvestigationActive(query.state.data) ? INVESTIGATION_POLL_MS : false),
    enabled: options.enabled,
  });

export function useCreateInvestigation(executionId: ID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: InvestigationCreateBody = {}) => api.createInvestigation(executionId, body),
    onSuccess: (investigation) => {
      // Showing the queued investigation at once starts the polling above.
      client.setQueryData(keys.investigation(executionId), investigation);
      void client.invalidateQueries({ queryKey: ["investigations", "list"] });
      void client.invalidateQueries({ queryKey: keys.trace(executionId) });
      void client.invalidateQueries({ queryKey: ["executions", "list"] });
    },
  });
}

export const useReplays = (params: ReplayListParams = {}, live: { refetchInterval?: number } = {}) =>
  useQuery({ queryKey: keys.replays(params), queryFn: () => api.listReplays(params), placeholderData: keepPreviousData, ...live });

/** A replay that has not finished: waiting for a worker, or being run by one. */
export const isReplayActive = (replay: Pick<Replay, "status"> | null | undefined): boolean =>
  replay?.status === "pending" || replay?.status === "claimed";

export const useReplay = (id: ID) =>
  useQuery({
    queryKey: keys.replay(id),
    queryFn: () => api.getReplay(id),
    refetchInterval: (query) => (isReplayActive(query.state.data) ? REPLAY_POLL_MS : false),
  });

export function useCreateReplay(executionId: ID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ReplayCreateBody) => api.createReplay(executionId, body),
    onSuccess: (replay) => {
      client.setQueryData(keys.replay(replay.id), replay);
      void client.invalidateQueries({ queryKey: ["replays", "list"] });
      void client.invalidateQueries({ queryKey: keys.trace(executionId) });
    },
  });
}

export function useUpdateAnomaly() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: ID; status: AnomalyStatus }) => api.updateAnomaly(id, { status }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["anomalies"] });
      void client.invalidateQueries({ queryKey: ["executions", "trace"] });
      void client.invalidateQueries({ queryKey: ["agents"] });
      void client.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}
