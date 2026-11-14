import { Suspense, type ReactNode } from "react";

import { Breadcrumbs } from "./breadcrumbs";
import { CommandPalette } from "./command-palette";
import { ModeBadge } from "./mode-badge";
import { Sidebar, SidebarFallback } from "./sidebar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="grid h-full grid-cols-[208px_minmax(0,1fr)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-raised focus:px-3 focus:py-1.5"
      >
        Skip to content
      </a>
      {/* The sidebar and breadcrumbs read the URL, which is only known per request. */}
      <Suspense fallback={<SidebarFallback />}>
        <Sidebar />
      </Suspense>
      <div className="flex min-w-0 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line-subtle px-5">
          <Suspense fallback={<span className="flex-1" />}>
            <Breadcrumbs />
          </Suspense>
          <ModeBadge />
          <CommandPalette />
        </header>
        <main id="main" tabIndex={-1} className="min-h-0 flex-1 overflow-y-auto outline-none">
          {children}
        </main>
      </div>
    </div>
  );
}
