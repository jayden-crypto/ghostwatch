"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { isActive, NAV_ITEMS } from "@/lib/nav";
import { cn } from "@/lib/utils";

function Wordmark() {
  return (
    <Link href="/" className="flex h-12 items-center gap-2 px-4 text-sm font-semibold tracking-tight">
      <svg viewBox="0 0 16 16" className="size-4" aria-hidden="true">
        <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="8" cy="8" r="2.25" fill="currentColor" />
      </svg>
      Ghostwatch
    </Link>
  );
}

function Frame({ pathname }: { pathname: string | null }) {
  return (
    <aside className="flex min-h-0 flex-col border-r border-line-subtle">
      <Wordmark />
      <nav aria-label="Main" className="flex flex-col gap-px px-2 py-2">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname !== null && isActive(href, pathname);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex h-8 items-center gap-2.5 rounded-md px-2 text-fg-muted transition-colors duration-150 ease-out hover:bg-raised hover:text-fg",
                active && "bg-raised font-medium text-fg",
              )}
            >
              <Icon className="size-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

export function Sidebar() {
  return <Frame pathname={usePathname()} />;
}

/** The same layout with nothing highlighted, shown until the URL is known. */
export function SidebarFallback() {
  return <Frame pathname={null} />;
}
