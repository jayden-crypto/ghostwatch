import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/errors";
import { createMockApi } from "@/lib/api/mock";
import { REPLAY_OUTCOMES, type Replay, type ReplayCreateBody } from "@/lib/api/types";
import { REPLAY_OUTCOME } from "@/lib/enums";
import { AUTHORIZATION_LABEL, SANDBOX_RULE, WORKER_COMMAND } from "@/lib/replay";
import { fixtures } from "@/mocks/fixtures";

let mock = createMockApi({ latency: () => 0, state: () => null });
/** Set by a test to make the next createReplay call fail the way the API would. */
let refusal: ApiError | null = null;
const created: ReplayCreateBody[] = [];
const api = new Proxy(
  {},
  {
    get: (_target, method: string) =>
      method === "createReplay"
        ? async (executionId: string, body: ReplayCreateBody) => {
            created.push(body);
            if (refusal) throw refusal;
            return mock.createReplay(executionId, body);
          }
        : (mock as unknown as Record<string, unknown>)[method],
  },
);
vi.mock("@/lib/api/client", () => ({ api }));
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

const { ReplayButton } = await import("@/components/replay/replay-dialog");
const { ReplayComparisonView, sourceCounts } = await import("@/components/replay/replay-comparison");
const { ReplayBody, ReplayView } = await import("@/components/replay/replay-view");
const { ReplaysView } = await import("@/components/replay/replays-view");

const wrap = (ui: ReactElement) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TooltipProvider>{ui}</TooltipProvider>
    </QueryClientProvider>,
  );

const fixed = fixtures["replays.get.fixed"];
const live = fixtures["replays.get.both_succeeded"];
const inconclusive = fixtures["replays.get.inconclusive"];
const finished = fixed.comparison!.original;
const comparison = (replay: Replay) => wrap(<ReplayComparisonView replay={replay} comparison={replay.comparison!} />);
const openDialog = async (user: ReturnType<typeof userEvent.setup>) => {
  wrap(<ReplayButton execution={finished} />);
  await user.click(screen.getByRole("button", { name: "Replay" }));
  return within(await screen.findByRole("dialog"));
};

beforeEach(() => {
  mock = createMockApi({ latency: () => 0, state: () => null });
  refusal = null;
  created.length = 0;
  push.mockClear();
  window.history.replaceState(null, "", "/");
});

describe("replay dialog", () => {
  it("defaults to sandbox, explains it in the contract's words, and asks for no authorization", async () => {
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    expect(dialog.getByRole("radio", { name: /^Sandbox/ })).toBeChecked();
    expect(dialog.getByRole("radio", { name: /^Live/ })).not.toBeChecked();
    expect(dialog.getByText(SANDBOX_RULE)).toBeInTheDocument();
    expect(dialog.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(dialog.getByText(/stays pending until one picks it up/)).toBeInTheDocument();
  });

  it("requests a sandbox replay without an authorization field and opens the new replay", async () => {
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    await user.type(dialog.getByLabelText(/^Note/), "  after the parser fix  ");
    await user.click(dialog.getByRole("button", { name: "Request sandbox replay" }));
    await waitFor(() => expect(push).toHaveBeenCalledTimes(1));
    expect(created).toEqual([{ mode: "sandbox", note: "after the parser fix" }]);
    expect(push.mock.calls[0][0]).toMatch(/^\/replays\/rpl_[0-9a-f]{32}$/);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("cannot request a live replay until the authorization box is ticked", async () => {
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    await user.click(dialog.getByRole("radio", { name: /^Live/ }));
    const submit = dialog.getByRole("button", { name: "Request live replay" });
    const box = dialog.getByRole("checkbox", { name: new RegExp(`^${AUTHORIZATION_LABEL}`) });
    expect(box).not.toBeChecked();
    expect(submit).toBeDisabled();
    await user.click(submit);
    expect(created).toEqual([]);

    await user.click(box);
    expect(submit).toBeEnabled();
    await user.click(submit);
    await waitFor(() => expect(push).toHaveBeenCalledTimes(1));
    expect(created).toEqual([{ mode: "live", authorize_side_effects: true }]);
  });

  it("forgets the authorization when the mode is changed away and back", async () => {
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    await user.click(dialog.getByRole("radio", { name: /^Live/ }));
    await user.click(dialog.getByRole("checkbox"));
    await user.click(dialog.getByRole("radio", { name: /^Sandbox/ }));
    expect(dialog.queryByRole("checkbox")).not.toBeInTheDocument();
    await user.click(dialog.getByRole("radio", { name: /^Live/ }));
    expect(dialog.getByRole("checkbox")).not.toBeChecked();
    expect(dialog.getByRole("button", { name: "Request live replay" })).toBeDisabled();
  });

  it("shows the API's side_effect_authorization_required refusal as it was sent", async () => {
    const user = userEvent.setup();
    const envelope = fixtures["error.side_effect_authorization_required"].error;
    refusal = new ApiError(envelope.code, envelope.message, 422, envelope.details);
    const dialog = await openDialog(user);
    await user.click(dialog.getByRole("radio", { name: /^Live/ }));
    await user.click(dialog.getByRole("checkbox"));
    await user.click(dialog.getByRole("button", { name: "Request live replay" }));
    const alert = await dialog.findByRole("alert");
    expect(alert).toHaveTextContent("authorization is required");
    expect(alert).toHaveTextContent(envelope.message);
    expect(alert).toHaveTextContent("side_effect_authorization_required · HTTP 422");
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("does not offer a replay of a run that is still in progress", () => {
    wrap(<ReplayButton execution={fixtures["executions.get.running"]} />);
    const button = screen.getByRole("button", { name: "Replay" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", expect.stringContaining("once it ends"));
  });
});

describe("comparison", () => {
  it("makes the outcome the headline and says what was recorded and what ran", () => {
    comparison(fixed);
    const banner = screen.getByRole("region", { name: "Outcome" });
    expect(banner).toHaveAttribute("data-outcome", "fixed");
    expect(within(banner).getByRole("heading", { name: "Fixed" })).toBeInTheDocument();
    expect(banner).toHaveTextContent("The original failed; the replay completed.");
    const counts = sourceCounts(fixed.comparison!.step_diffs);
    expect(counts).toEqual({ recorded: 1, executed: 3, blocked: 0 });
    expect(within(banner).getByTestId("replay-sources")).toHaveTextContent(
      "Sandbox replay. Of the replay's 4 steps: 1 served from the recording, 3 really ran, 0 blocked.",
    );
    expect(banner).toHaveTextContent(SANDBOX_RULE);
  });

  it("gives every outcome its own label, and only fixed the filled green frame", () => {
    const frames = REPLAY_OUTCOMES.map((outcome) => {
      const replay = fixtures[`replays.get.${outcome}`];
      expect(replay.comparison!.outcome).toBe(outcome);
      const { unmount } = comparison(replay);
      const banner = screen.getByRole("region", { name: "Outcome" });
      expect(within(banner).getByRole("heading", { name: REPLAY_OUTCOME[outcome].label })).toBeInTheDocument();
      const frame = banner.className;
      unmount();
      return frame;
    });
    expect(new Set(frames).size).toBe(REPLAY_OUTCOMES.length);
    expect(frames.filter((frame) => frame.includes("bg-completed"))).toHaveLength(1);
    expect(frames[REPLAY_OUTCOMES.indexOf("fixed")]).toContain("bg-completed");
  });

  it("puts the original and the replay side by side with the API's deltas", () => {
    comparison(fixed);
    const table = within(screen.getByRole("table", { name: /side by side/ }));
    const row = (name: string) => within(table.getByRole("row", { name: new RegExp(`^${name}`) }));
    expect(row("Status").getByText("Failed")).toBeInTheDocument();
    expect(row("Status").getByText("Completed")).toBeInTheDocument();
    expect(row("Duration").getByText("+121 ms")).toBeInTheDocument();
    expect(row("Steps").getByText("+1")).toBeInTheDocument();
    // tokens_delta is null in this fixture: unknown stays a dash, never a zero.
    expect(fixed.comparison!.tokens_delta).toBeNull();
    expect(row("Tokens").queryByText("0")).not.toBeInTheDocument();
    expect(row("Error").getByText("KeyError")).toBeInTheDocument();
    expect(row("Error").getByText("None")).toBeInTheDocument();
    const { original, replay } = fixed.comparison!;
    expect(row("Trace").getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([`/executions/${original.id}`, `/executions/${replay.id}`]);
  });

  it("aligns the steps, marks the rows that differ, and links each side to its own step", () => {
    comparison(fixed);
    const table = screen.getByRole("table", { name: /^Step-by-step/ });
    const rows = within(table).getAllByRole("row").slice(1);
    const diffs = fixed.comparison!.step_diffs;
    expect(rows.map((row) => row.getAttribute("data-change"))).toEqual(diffs.map((diff) => diff.change));
    expect(screen.getByRole("heading", { name: /^Steps/ })).toHaveTextContent("2 of 4 differ");

    const parse = within(within(table).getByRole("row", { name: /parse_results/ }));
    expect(parse.getByText("Status changed")).toBeInTheDocument();
    expect(parse.getByRole("link", { name: "Open step parse_results in the original" })).toHaveAttribute(
      "href",
      `/executions/${fixed.comparison!.original.id}?step=${diffs[2].original_step_id}`,
    );
    expect(parse.getByRole("link", { name: "Open step parse_results in the replay" })).toHaveAttribute(
      "href",
      `/executions/${fixed.comparison!.replay.id}?step=${diffs[2].replay_step_id}`,
    );

    const added = within(within(table).getByRole("row", { name: /summarize/ }));
    expect(added.getByText("Not in the original")).toBeInTheDocument();
    expect(added.getByText("Added")).toBeInTheDocument();
    // What really happened to each replay step is on its row.
    expect(within(within(table).getByRole("row", { name: /web_search/ })).getByText("Recorded")).toBeInTheDocument();
    expect(added.getByText("Executed")).toBeInTheDocument();
  });

  it("shows a blocked step as blocked, and a step the replay never reached as not in the replay", () => {
    comparison(inconclusive);
    const table = screen.getByRole("table", { name: /^Step-by-step/ });
    const blocked = inconclusive.comparison!.step_diffs.filter((diff) => diff.replay_source === "blocked");
    expect(blocked.length).toBeGreaterThan(0);
    for (const diff of blocked) {
      expect(within(within(table).getByRole("row", { name: new RegExp(`^${diff.ordinal} ${diff.name}`) })).getByText("Blocked")).toBeInTheDocument();
    }
    expect(screen.getByTestId("replay-sources")).toHaveTextContent(`${blocked.length} blocked`);
  });

  it("labels a live replay as live with side effects authorized, not as a sandbox", () => {
    comparison(live);
    const sources = screen.getByTestId("replay-sources");
    expect(sources).toHaveTextContent("Live replay, side effects authorized.");
    expect(sources).not.toHaveTextContent("Sandbox");
    const removed = live.comparison!.step_diffs.find((diff) => diff.change === "removed")!;
    const row = within(screen.getByRole("row", { name: new RegExp(`^${removed.ordinal} ${removed.name}`) }));
    expect(row.getByText("Not in the replay")).toBeInTheDocument();
  });
});

describe("replay states", () => {
  it("pending: says a worker has to pick it up, and how to start one", () => {
    wrap(<ReplayBody replay={fixtures["replays.get.pending"]} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Waiting for a replay worker");
    expect(status).toHaveTextContent(WORKER_COMMAND);
    expect(status).toHaveTextContent("checking every 2 s");
    expect(screen.queryByRole("region", { name: "Outcome" })).not.toBeInTheDocument();
  });

  it("claimed: says a worker is running it and the comparison comes when the run ends", () => {
    wrap(<ReplayBody replay={fixtures["replays.get.claimed"]} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("A worker is replaying the run");
    expect(status).not.toHaveTextContent(WORKER_COMMAND);
  });

  it("failed: shows the worker's error as a failure of the replay, not a result", () => {
    const failed = fixtures["replays.get.failed"];
    wrap(<ReplayBody replay={failed} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The replay could not be run");
    expect(alert).toHaveTextContent(failed.error!.type);
    expect(alert).toHaveTextContent(failed.error!.message);
    expect(alert).toHaveTextContent("This says nothing about the agent");
  });

  it("loads a replay by id with its note, mode and links to both traces", async () => {
    wrap(<ReplayView replayId={fixed.id} />);
    expect(await screen.findByRole("region", { name: "Outcome" })).toHaveAttribute("data-outcome", "fixed");
    expect(screen.getByText(`“${fixed.note}”`)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Original trace" })).toHaveAttribute("href", `/executions/${fixed.original_execution_id}`);
    expect(screen.getByRole("link", { name: "Replay trace" })).toHaveAttribute("href", `/executions/${fixed.replay_execution_id}`);
  });

  it("says so when the replay does not exist", async () => {
    wrap(<ReplayView replayId="rpl_ffffffffffffffffffffffffffffffff" />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Replay not found");
    expect(within(alert).queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});

describe("replays list", () => {
  it("lists every replay with its status, outcome and mode, linking each row to its page", async () => {
    wrap(<ReplaysView />);
    const table = await screen.findByRole("table", { name: "Replays" });
    const all = fixtures["replays.list"].items;
    await waitFor(() => expect(within(table).getAllByRole("link", { name: /^Open replay / })).toHaveLength(all.length));
    expect(within(table).getByRole("link", { name: `Open replay ${fixed.id}` })).toHaveAttribute("href", `/replays/${fixed.id}`);
    for (const outcome of REPLAY_OUTCOMES) expect(within(table).getByText(REPLAY_OUTCOME[outcome].label)).toBeInTheDocument();
    // A replay that has not been compared says so instead of showing an outcome.
    expect(within(table).getAllByText("Not compared yet")).toHaveLength(all.filter((replay) => !replay.comparison && !replay.error).length);
    expect(within(table).getByText(fixtures["replays.get.failed"].error!.type)).toBeInTheDocument();
  });

  it("narrows to the replays of one execution from the URL, and can widen again", async () => {
    const user = userEvent.setup();
    const original = fixed.original_execution_id;
    const expected = fixtures["replays.list"].items.filter((replay) => replay.original_execution_id === original).length;
    window.history.replaceState(null, "", `/replays?original_execution_id=${original}`);
    const view = wrap(<ReplaysView />);
    const table = await screen.findByRole("table", { name: "Replays" });
    await waitFor(() => expect(within(table).getAllByRole("link", { name: /^Open replay / })).toHaveLength(expected));
    await user.click(screen.getByRole("button", { name: "Show replays of every execution" }));
    expect(window.location.search).toBe("");
    view.unmount();
  });

  it("explains how to make a replay when there are none", async () => {
    mock = createMockApi({ latency: () => 0, state: () => "empty" });
    wrap(<ReplaysView />);
    expect(await screen.findByText("No replays yet")).toBeInTheDocument();
  });
});
