import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { createMockApi } from "@/lib/api/mock";

let failure: ApiError = new ApiError("validation_error", "Request validation failed.", 422);
const calls: string[] = [];
const base = createMockApi({ latency: () => 0, state: () => null });
const api = {
  ...base,
  listExecutions: async () => {
    calls.push("listExecutions");
    throw failure;
  },
};
vi.mock("@/lib/api/client", () => ({ api }));

const { LIST_POLL_MS, pollEvery, useExecutions } = await import("@/lib/api/hooks");

function Probe() {
  const { error } = useExecutions({}, { refetchInterval: LIST_POLL_MS });
  return <p>{error ? `error ${(error as ApiError).code}` : "loading"}</p>;
}

/** Renders a polling list whose request always fails with `failure`, then lets two poll intervals pass. */
async function requestsOverTwoIntervals(): Promise<number> {
  vi.useFakeTimers();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Probe />
    </QueryClientProvider>,
  );
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(screen.getByText(`error ${failure.code}`)).toBeInTheDocument();
  const before = calls.length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2 * LIST_POLL_MS + 100);
  });
  return calls.length - before;
}

afterEach(() => {
  vi.useRealTimers();
  calls.length = 0;
});

describe("list polling", () => {
  it("pauses on a 4xx, keeps going on a network error or a 5xx", () => {
    const poll = pollEvery(LIST_POLL_MS)!;
    const at = (error: unknown) => poll({ state: { error } });
    expect(at(null)).toBe(LIST_POLL_MS);
    expect(at(new ApiError("validation_error", "bad", 422))).toBe(false);
    expect(at(new ApiError("not_found", "gone", 404))).toBe(false);
    expect(at(new ApiError("network_error", "down", null))).toBe(LIST_POLL_MS);
    expect(at(new ApiError("internal_error", "boom", 500))).toBe(LIST_POLL_MS);
    expect(pollEvery(undefined)).toBeUndefined();
  });

  it("does not repeat a request that failed with a 422", async () => {
    failure = new ApiError("validation_error", "Request validation failed.", 422);
    expect(await requestsOverTwoIntervals()).toBe(0);
  });

  it("keeps asking while the backend cannot be reached, so the page recovers by itself", async () => {
    failure = new ApiError("network_error", "Could not reach the Ghostwatch API.", null);
    expect(await requestsOverTwoIntervals()).toBe(2);
  });
});
