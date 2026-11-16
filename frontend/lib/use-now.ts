"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

/**
 * The current time, shared by every relative timestamp on the page and refreshed every 10 s.
 * `null` on the server and during hydration, where "now" is not known: callers show the exact
 * time instead.
 */
let now = Date.now();
let timer: ReturnType<typeof setInterval> | undefined;
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (timer === undefined) {
    now = Date.now();
    timer = setInterval(() => {
      now = Date.now();
      for (const notify of listeners) notify();
    }, 10_000);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

export function useNow(): number | null {
  return useSyncExternalStore(
    subscribe,
    () => now,
    () => null,
  );
}

/** Milliseconds since `since`, updated every second. Null until mounted, where "now" is not known. */
export function useElapsed(since: string): number | null {
  const [current, setCurrent] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setCurrent(Date.now());
    const first = setTimeout(tick, 0);
    const every = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(every);
    };
  }, []);
  return current === null ? null : Math.max(0, current - Date.parse(since));
}
