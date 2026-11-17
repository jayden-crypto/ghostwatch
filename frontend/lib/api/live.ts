/** The live adapter: `fetch` against NEXT_PUBLIC_API_BASE_URL, exactly as contract/API_CONTRACT.md describes. */
import type { GhostwatchApi } from "./client";
import { API_BASE_URL } from "./config";
import { ApiError, parseErrorEnvelope } from "./errors";

type QueryValue = string | number | boolean | readonly string[] | undefined;

/** Contract query string: lists are comma-separated, absent and empty values are left out. */
export function toQuery(params: object | undefined): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries((params ?? {}) as Record<string, QueryValue>)) {
    if (value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      if (value.length) search.set(key, value.join(","));
    } else {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function createLiveApi(baseUrl: string, fetcher: typeof fetch = fetch): GhostwatchApi {
  async function request<T>(method: "GET" | "POST" | "PATCH", path: string, body?: unknown): Promise<T> {
    const url = `${baseUrl}${path}`;
    let response: Response;
    try {
      response = await fetcher(url, {
        method,
        headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: "no-store",
      });
    } catch {
      throw new ApiError("network_error", `Could not reach the Ghostwatch API at ${baseUrl}. Is the backend running?`);
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new ApiError("invalid_response", `${method} ${path} answered HTTP ${response.status} without a JSON body.`, response.status);
    }
    if (response.ok) return payload as T;

    const envelope = parseErrorEnvelope(payload);
    if (!envelope) {
      throw new ApiError(
        "invalid_response",
        `${method} ${path} answered HTTP ${response.status} without the contract's error envelope.`,
        response.status,
      );
    }
    throw new ApiError(envelope.code, envelope.message, response.status, envelope.details);
  }

  const id = encodeURIComponent;
  return {
    health: () => request("GET", "/health"),
    listAgents: (params) => request("GET", `/agents${toQuery(params)}`),
    getAgent: (agentId) => request("GET", `/agents/${id(agentId)}`),
    listExecutions: (params) => request("GET", `/executions${toQuery(params)}`),
    getExecution: (executionId) => request("GET", `/executions/${id(executionId)}`),
    getTrace: (executionId) => request("GET", `/executions/${id(executionId)}/trace`),
    listEvents: (executionId, params) => request("GET", `/executions/${id(executionId)}/events${toQuery(params)}`),
    statsOverview: (window) => request("GET", `/stats/overview${toQuery({ window })}`),
    statsTimeseries: (params) => request("GET", `/stats/timeseries${toQuery(params)}`),
    listAnomalies: (params) => request("GET", `/anomalies${toQuery(params)}`),
    getAnomaly: (anomalyId) => request("GET", `/anomalies/${id(anomalyId)}`),
    updateAnomaly: (anomalyId, body) => request("PATCH", `/anomalies/${id(anomalyId)}`, body),
    listInvestigations: (params) => request("GET", `/investigations${toQuery(params)}`),
    getInvestigation: (executionId) => request("GET", `/investigations/${id(executionId)}`),
    createInvestigation: (executionId, body) => request("POST", `/investigations/${id(executionId)}`, body ?? {}),
    listReplays: (params) => request("GET", `/replays${toQuery(params)}`),
    getReplay: (replayId) => request("GET", `/replays/${id(replayId)}`),
    createReplay: (executionId, body) => request("POST", `/executions/${id(executionId)}/replay`, body),
  };
}

export const liveApi = createLiveApi(API_BASE_URL);
