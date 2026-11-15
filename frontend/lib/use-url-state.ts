"use client";

import { useSearchParams } from "next/navigation";
import { useCallback } from "react";

export type UrlPatch = Record<string, string | null | undefined>;

/** The current URL with `patch` applied to its query string. `null`, `undefined` and "" remove a key. */
export function withParams(patch: UrlPatch, pathname = window.location.pathname, search = window.location.search): string {
  const next = new URLSearchParams(search);
  for (const [key, value] of Object.entries(patch)) {
    if (value == null || value === "") next.delete(key);
    else next.set(key, value);
  }
  const query = next.toString();
  return `${pathname}${query ? `?${query}` : ""}`;
}

/**
 * URL is state: filters, the selected step and tabs live in the query string, so every view is
 * linkable. Returns the current params and a setter that patches them in place.
 *
 * The setter uses the History API, which Next's router observes, so components that read
 * `useSearchParams` re-render without a navigation. `replace` (the default) is for changes that
 * should not fill the back stack, such as moving through steps; `push` is for ones that should.
 */
export function useUrlState() {
  const params = useSearchParams();
  const setParams = useCallback((patch: UrlPatch, mode: "replace" | "push" = "replace") => {
    const url = withParams(patch);
    if (url === `${window.location.pathname}${window.location.search}`) return;
    if (mode === "push") window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
  }, []);
  return [params, setParams] as const;
}
