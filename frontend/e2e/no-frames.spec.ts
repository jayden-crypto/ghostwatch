import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import type { Agent, Investigation, Replay, Trace } from "../lib/api/types";

/**
 * Pages with an id in their path must load in a window that draws no frames: a browser pane or tab that
 * is not on screen. React reveals server-streamed content on an animation frame, so a page whose body
 * streams in would stay empty there and never fetch its data until shown. Animation frames are switched
 * off before any page script runs.
 */
const fixture = <T>(name: string): T => JSON.parse(readFileSync(join(__dirname, "..", "..", "contract", "fixtures", `${name}.json`), "utf8")) as T;

const investigation = fixture<Investigation>("investigations.get.confirmed");
const trace = fixture<Trace>(`executions.trace.${investigation.execution_id}`);
const replay = fixture<Replay>("replays.get.fixed");
const agent = fixture<Agent>("agents.get.research-assistant");

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.requestAnimationFrame = () => 0;
  });
});

test("the trace page loads without animation frames", async ({ page }) => {
  await page.goto(`/executions/${trace.execution.id}`);
  await expect(page.locator(`[data-step-id="${trace.steps[0].id}"]`).first()).toBeAttached();
});

test("the replay page loads without animation frames", async ({ page }) => {
  await page.goto(`/replays/${replay.id}`);
  await expect(page.locator('[aria-label="Outcome"]')).toHaveAttribute("data-outcome", "fixed");
});

test("the agent page loads without animation frames", async ({ page }) => {
  await page.goto(`/agents/${agent.id}`);
  await expect(page.locator("main")).toContainText(agent.name);
});

test("the investigation page loads without animation frames", async ({ page }) => {
  await page.goto(`/investigations/${investigation.execution_id}`);
  await expect(page.locator("main")).toContainText(investigation.report!.facts[0].statement);
});
