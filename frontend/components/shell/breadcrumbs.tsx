"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import { NAV_ITEMS } from "@/lib/nav";

/** `exe_3f9c…3a2b`: enough of an id to recognise it. The full id is on the page itself. */
const shorten = (segment: string): string =>
  /^[a-z]{3}_[0-9a-f]{32}$/.test(segment) ? `${segment.slice(0, 8)}…${segment.slice(-4)}` : segment;

export function Breadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  const section = NAV_ITEMS.find((item) => item.href === `/${segments[0] ?? ""}`);
  const crumbs = [
    { href: section?.href ?? "/", label: section?.label ?? segments[0] ?? "Overview", mono: false },
    ...segments.slice(1).map((segment, index) => ({
      href: `/${segments.slice(0, index + 2).join("/")}`,
      label: shorten(segment),
      mono: true,
    })),
  ];
  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 items-center gap-1.5 text-fg-muted">
      {crumbs.map((crumb, index) => {
        const last = index === crumbs.length - 1;
        return (
          <Fragment key={crumb.href}>
            {index > 0 && (
              <span aria-hidden="true" className="text-fg-subtle">
                /
              </span>
            )}
            {last ? (
              <span
                aria-current="page"
                className={crumb.mono ? "truncate font-mono text-xs text-fg" : "truncate font-medium text-fg"}
              >
                {crumb.label}
              </span>
            ) : (
              <Link href={crumb.href} className="rounded-sm hover:text-fg">
                {crumb.label}
              </Link>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
