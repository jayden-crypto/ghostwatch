import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import type { Replay } from "../lib/api/types";

/**
 * The replay part of the demo in mock mode: from the failed run to its replays, to the comparison
 * that says the fix worked; then a new sandbox replay, which waits for a worker.
 */
const fixture = <T>(name: string): T => JSON.parse(readFileSync(join(__dirname, "..", "..", "contract", "fixtures", `${name}.json`), "utf8")) as T;

const fixed = fixture<Replay>("replays.get.fixed");
const comparison = fixed.comparison!;

test("failed execution → its replays → the comparison with outcome fixed", async ({ page }) => {
  await page.goto(`/executions/${fixed.original_execution_id}`);
  await page.getByRole("link", { name: /^Replayed \d+×$/ }).click();
  await expect(page).toHaveURL(new RegExp(`/replays\\?original_execution_id=${fixed.original_execution_id}$`));

  const table = page.getByRole("table", { name: "Replays" });
  // The row is one link with the execution id links on top of it, so click it where a row is only a row.
  await table.getByRole("link", { name: `Open replay ${fixed.id}` }).click({ position: { x: 24, y: 12 } });
  await expect(page).toHaveURL(new RegExp(`/replays/${fixed.id}$`));

  const outcome = page.getByRole("region", { name: "Outcome" });
  await expect(outcome).toHaveAttribute("data-outcome", "fixed");
  await expect(outcome.getByRole("heading", { name: "Fixed" })).toBeVisible();
  await expect(outcome).toContainText("Sandbox replay.");

  const steps = page.getByRole("table", { name: /^Step-by-step/ });
  await expect(steps.locator("tbody tr")).toHaveCount(comparison.step_diffs.length);
  await expect(steps.locator('tbody tr:not([data-change="unchanged"])')).toHaveCount(comparison.step_diffs.filter((diff) => diff.change !== "unchanged").length);

  // A replay step links into the replay's own trace.
  const changed = comparison.step_diffs.find((diff) => diff.change === "status_changed")!;
  await steps.getByRole("link", { name: `Open step ${changed.name} in the replay` }).click();
  await expect(page).toHaveURL(new RegExp(`/executions/${comparison.replay.id}\\?step=${changed.replay_step_id}$`));
  await expect(page.getByRole("tree", { name: "Execution steps" }).locator('[aria-selected="true"]')).toHaveAttribute("data-step-id", changed.replay_step_id!);
});

test("a live replay needs authorization; a sandbox replay is requested and waits for a worker", async ({ page }) => {
  await page.goto(`/executions/${fixed.original_execution_id}`);
  await page.getByRole("button", { name: "Replay", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Replay this execution" });
  await expect(dialog.getByRole("radio", { name: /^Sandbox/ })).toBeChecked();

  // The radios are visually hidden inside their cards; a user clicks the card.
  await dialog.locator("label").filter({ hasText: /^Live/ }).click();
  await expect(dialog.getByRole("radio", { name: /^Live/ })).toBeChecked();
  const submitLive = dialog.getByRole("button", { name: "Request live replay" });
  await expect(submitLive).toBeDisabled();
  await dialog.getByRole("checkbox", { name: /^I authorize real external side effects for this replay/ }).click();
  await expect(submitLive).toBeEnabled();

  await dialog.locator("label").filter({ hasText: /^Sandbox/ }).click();
  await expect(dialog.getByRole("radio", { name: /^Sandbox/ })).toBeChecked();
  await dialog.getByRole("button", { name: "Request sandbox replay" }).click();
  await expect(page).toHaveURL(/\/replays\/rpl_[0-9a-f]{32}$/);
  const waiting = page.getByRole("status").filter({ hasText: "Waiting for a replay worker" });
  await expect(waiting).toBeVisible();
  await expect(waiting).toContainText("replay.py worker");
});
