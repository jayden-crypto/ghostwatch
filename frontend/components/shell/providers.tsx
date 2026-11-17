"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";

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
