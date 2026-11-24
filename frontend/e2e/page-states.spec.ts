import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect as baseExpect, test, type Page } from "@playwright/test";

import type { Agent, Investigation, Replay } from "../lib/api/types";

/**
 * Every page has a loading, an empty and an error state (plan §10). The mock answers each request
 * after 150–400 ms, `?__state=empty` empties its world and `?__state=error` fails every request with
 * a 500. A page with an id in its path has no "empty" view: with nothing stored, its id does not
 * exist, so it shows its not-found state. /settings has no empty state: it shows one health report.
 *
 * These 35 tests all start against a server that has just started. Measured on a 16-core Windows machine,
 * a page's data was on screen 0.2–1.1 s after `goto` with one worker, but 1.6–5.3 s with the default
 * 8 workers, so the default 5 s was too short. 15 s leaves room without hiding a page that never loads.
 */
const expect = baseExpect.configure({ timeout: 15_000 });
const fixture = <T>(name: string): T => JSON.parse(readFileSync(join(__dirname, "..", "..", "contract", "fixtures", `${name}.json`), "utf8")) as T;

const investigation = fixture<Investigation>("investigations.get.confirmed");
const replay = fixture<Replay>("replays.get.fixed");
const agent = fixture<Agent>("agents.get.research-assistant");

const pages: { path: string; loaded: string; empty?: string; error: string }[] = [
  { path: "/", loaded: "Success rate", empty: "No executions yet", error: "Totals could not be loaded" },
  { path: "/agents", loaded: agent.name, empty: "No agents registered", error: "Agents could not be loaded" },
  { path: `/agents/${agent.id}`, loaded: agent.name, empty: "This agent does not exist", error: "This agent could not be loaded" },
  { path: "/executions", loaded: "41 executions", empty: "No executions yet", error: "Executions could not be loaded" },
  { path: `/executions/${investigation.execution_id}`, loaded: "Waterfall", empty: "This execution does not exist", error: "This trace could not be loaded" },
  { path: "/traces", loaded: agent.name, empty: "No traces yet", error: "Recent traces could not be loaded" },
  { path: "/anomalies", loaded: "10 anomalies", empty: "No open anomalies", error: "Anomalies could not be loaded" },
  { path: "/investigations", loaded: "11 investigations", empty: "No investigations yet", error: "Investigations could not be loaded" },
  { path: `/investigations/${investigation.execution_id}`, loaded: "Confirmed root cause", empty: "This execution does not exist", error: "The investigation could not be loaded" },
  { path: "/replays", loaded: "9 replays", empty: "No replays yet", error: "Replays could not be loaded" },
  { path: `/replays/${replay.id}`, loaded: "Original trace", empty: "This replay does not exist", error: "The replay could not be loaded" },
  { path: "/settings", loaded: "Backend", error: "The backend did not answer the health check" },
];

/** Records whether a skeleton was ever on the page, however briefly. */
async function watchSkeletons(page: Page) {
  await page.addInitScript(() => {
    const seen = window as unknown as { __skeletonSeen: boolean };
    seen.__skeletonSeen = false;
    new MutationObserver(() => {
      if (document.querySelector('[data-slot="skeleton"]')) seen.__skeletonSeen = true;
    }).observe(document, { subtree: true, childList: true });
  });
}

for (const { path, loaded, empty, error } of pages) {
  test.describe(path, () => {
    test("shows skeletons while loading, then the data", async ({ page }) => {
      await watchSkeletons(page);
      await page.goto(path);
      await expect(page.locator("main")).toContainText(loaded);
      await expect(page.locator('main [data-slot="skeleton"]')).toHaveCount(0);
      expect(await page.evaluate(() => (window as unknown as { __skeletonSeen: boolean }).__skeletonSeen)).toBe(true);
    });

    if (empty) {
      test("says so when there is nothing to show", async ({ page }) => {
        await page.goto(`${path}?__state=empty`);
        await expect(page.locator("main")).toContainText(empty);
        await expect(page.getByRole("alert").filter({ hasText: "internal_error" })).toHaveCount(0);
      });
    }

    test("shows the API's error and a way to retry", async ({ page }) => {
      await page.goto(`${path}?__state=error`);
      const alert = page.getByRole("alert").filter({ hasText: error });
      await expect(alert).toContainText("internal_error · HTTP 500");
      await expect(alert.getByRole("button", { name: "Retry" })).toBeVisible();
    });
  });
}
