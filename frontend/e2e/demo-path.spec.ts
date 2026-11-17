import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import type { Investigation, Trace } from "../lib/api/types";

/**
 * The demo path (PROJECT_PLAN.md §5) in mock mode: overview → the failed run → its investigation →
 * a fact's evidence → the exact step, highlighted in the waterfall.
 *
 * Every expected value is read from the contract fixtures the mock adapter serves, so the test
 * follows the data instead of repeating it.
 */
const fixture = <T>(name: string): T => JSON.parse(readFileSync(join(__dirname, "..", "..", "contract", "fixtures", `${name}.json`), "utf8")) as T;

const investigation = fixture<Investigation>("investigations.get.confirmed");
const report = investigation.report!;
const executionId = investigation.execution_id;
const trace = fixture<Trace>(`executions.trace.${executionId}`);
const failingStep = trace.steps.find((step) => step.id === report.failing_step_id)!;

test("overview → failed execution → investigation → evidence → highlighted step", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });

  // 1. Overview: the failed run is among the recent executions.
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  const recent = page.getByRole("table", { name: "Recent executions" });
  await recent.getByRole("link", { name: new RegExp(`execution ${executionId}$`) }).click();

  // 2. The trace: the failed run with its error, and no step selected yet.
  await expect(page).toHaveURL(new RegExp(`/executions/${executionId}$`));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(trace.execution.agent_name);
  await expect(page.getByText(trace.execution.error!.message, { exact: true })).toBeVisible();
  const steps = page.getByRole("tree", { name: "Execution steps" });
  await expect(steps.getByRole("treeitem")).toHaveCount(trace.steps.length);
  await expect(steps.locator('[aria-selected="true"]')).toHaveCount(0);

  // 3. Its investigation: a confirmed root cause, named by a deterministic signature.
  await page.getByRole("link", { name: "Investigation", exact: true }).click();
  await expect(page).toHaveURL(/tab=investigation/);
  const rootCause = page.getByRole("region", { name: "Root cause" });
  await expect(rootCause).toHaveAttribute("data-root-cause", "confirmed");
  await expect(rootCause.getByRole("heading", { name: "Confirmed root cause" })).toBeVisible();
  await expect(rootCause).toContainText(report.root_cause.statement);
  await expect(rootCause).toContainText(report.root_cause.signature!);

  // 4. A fact's evidence links to the failing step.
  const facts = page.getByRole("region", { name: /^Facts/ });
  await expect(facts.getByText(report.facts[0].statement)).toBeVisible();
  await facts.locator(`a[href="/executions/${executionId}?step=${failingStep.id}"]`).first().click();

  // 5. The waterfall opens with exactly that step selected, and the inspector shows it.
  await expect(page).toHaveURL(new RegExp(`/executions/${executionId}\\?step=${failingStep.id}$`));
  const selected = steps.locator('[aria-selected="true"]');
  await expect(selected).toHaveCount(1);
  await expect(selected).toHaveAttribute("data-step-id", failingStep.id);
  await expect(selected).toBeInViewport();
  const inspector = page.getByRole("complementary", { name: `Step ${failingStep.name}` });
  await expect(inspector).toBeVisible();
  await inspector.getByRole("tab", { name: "Error" }).click();
  await expect(inspector.getByRole("tabpanel")).toContainText(failingStep.error!.type);
  await expect(inspector.getByRole("tabpanel")).toContainText(failingStep.error!.message);

  expect(errors, "page and console errors on the demo path").toEqual([]);
});
