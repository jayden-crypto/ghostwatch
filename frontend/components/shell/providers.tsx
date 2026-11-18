"use client";

import { notifyManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";

// TanStack Query hands finished requests to components with setTimeout(0) by default. Browsers throttle
// timers in a hidden tab or pane (to once a second, or once a minute after a while), so a response that
// had already arrived could leave the page on its skeleton for seconds. A microtask is never throttled
// and still batches every update made in the same task.
notifyManager.setScheduler(queueMicrotask);

let browserQueryClient: QueryClient | undefined;

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Lists are cheap to refetch and the data changes under us; views that poll set their own interval.
        staleTime: 5_000,
        refetchOnWindowFocus: false,
        // An error is shown with a Retry button rather than retried silently, so failures stay visible.
        retry: false,
      },
    },
  });
}

function getQueryClient(): QueryClient {
  // A new client per server render keeps requests isolated; the browser keeps one cache.
  if (typeof window === "undefined") return makeQueryClient();
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={getQueryClient()}>
      <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
    </QueryClientProvider>
  );
}
