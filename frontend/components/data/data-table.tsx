"use client";

/**
 * The dense table every list uses: 34 px rows, right-aligned numbers, server-driven sorting, a
 * skeleton with the final layout while loading, and whole-row links that stay real links.
 */
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCount } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface Column<T> {
  id: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  align?: "left" | "right";
  /** The contract `sort` field this column sorts by; omitted for columns the API cannot sort. */
  sortKey?: string;
  /** Tailwind width class, e.g. `w-32`. Unsized columns share what is left. */
  width?: string;
  /** Width of this column's skeleton bar. */
  skeleton?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  /** `undefined` while the first page loads. */
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  /** Makes each row a link. The link lives in the first cell and covers the row. */
  rowHref?: (row: T) => string;
  /** Accessible name of a row's link. */
  rowLabel?: (row: T) => string;
  /** The contract's `sort` value, e.g. `-started_at`. */
  sort?: string;
  onSortChange?: (sort: string) => void;
  /** Shown instead of rows when there are none. */
  empty: ReactNode;
  caption: string;
  skeletonRows?: number;
  /** Rows are from a previous request while a new one loads. */
  stale?: boolean;
  selectedKey?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  rowHref,
  rowLabel,
  sort,
  onSortChange,
  empty,
  caption,
  skeletonRows = 8,
  stale = false,
  selectedKey,
}: DataTableProps<T>) {
  if (rows && rows.length === 0) return <>{empty}</>;
  const sortField = sort?.replace(/^-/, "");
  const descending = sort?.startsWith("-") ?? false;
  return (
    <div className="overflow-x-auto">
      <table className={cn("w-full border-collapse text-left transition-opacity duration-150", stale && "opacity-60")}>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line-subtle">
            {columns.map((column) => {
              const active = column.sortKey !== undefined && column.sortKey === sortField;
              const SortIcon = active ? (descending ? ArrowDown : ArrowUp) : ArrowUpDown;
              return (
                <th
                  key={column.id}
                  scope="col"
                  aria-sort={active ? (descending ? "descending" : "ascending") : undefined}
                  className={cn(
                    "h-8 whitespace-nowrap px-3 text-xs font-medium text-fg-subtle first:pl-4 last:pr-4",
                    column.align === "right" && "text-right",
                    column.width,
                  )}
                >
                  {column.sortKey && onSortChange ? (
                    <button
                      type="button"
                      // Newest, longest and largest first is what people look for, so a column starts descending.
                      onClick={() => onSortChange(active && descending ? column.sortKey! : `-${column.sortKey}`)}
                      className={cn(
                        "inline-flex items-center gap-1 rounded-sm hover:text-fg",
                        column.align === "right" && "flex-row-reverse",
                        active && "text-fg",
                      )}
                    >
                      {column.header}
                      <SortIcon className={cn("size-3", !active && "opacity-50")} aria-hidden="true" />
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows === undefined
            ? Array.from({ length: skeletonRows }, (_, index) => (
                <tr key={index} className="border-b border-line-subtle last:border-0">
                  {columns.map((column) => (
                    <td key={column.id} className="h-[34px] px-3 first:pl-4 last:pr-4">
                      <Skeleton className={cn("h-3", column.skeleton ?? "w-20", column.align === "right" && "ml-auto")} />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row) => {
                const key = rowKey(row);
                const href = rowHref?.(row);
                return (
                  <tr
                    key={key}
                    data-selected={key === selectedKey || undefined}
                    className={cn(
                      "group/row relative border-b border-line-subtle transition-colors duration-150 ease-out last:border-0 data-selected:bg-raised",
                      href && "hover:bg-raised has-[a.row-link:focus-visible]:bg-raised",
                    )}
                  >
                    {columns.map((column, index) => (
                      <td
                        key={column.id}
                        className={cn(
                          "h-[34px] whitespace-nowrap px-3 first:pl-4 last:pr-4",
                          column.align === "right" && "text-right",
                        )}
                      >
                        {index === 0 && href ? (
                          <>
                            {/* Covers the row, so the whole row is one link; inner links and buttons sit above it. */}
                            <Link href={href} aria-label={rowLabel?.(row)} className="row-link absolute inset-0 focus-visible:-outline-offset-2" />
                            {column.cell(row)}
                          </>
                        ) : (
                          column.cell(row)
                        )}
                      </td>
                    ))}
                  </tr>
                );
              })}
        </tbody>
      </table>
    </div>
  );
}

/** "1–50 of 213" with previous and next. Offsets are the contract's. */
export function Pagination({
  total,
  limit,
  offset,
  onOffsetChange,
  noun,
}: {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
  noun: string;
}) {
  if (total === 0) return null;
  const last = Math.min(total, offset + limit);
  return (
    <div className="flex h-10 items-center justify-between gap-3 border-t border-line-subtle px-4 text-xs text-fg-muted">
      <span className="num">
        {formatCount(offset + 1)}–{formatCount(last)} of {formatCount(total)} {noun}
      </span>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon-sm" aria-label="Previous page" disabled={offset === 0} onClick={() => onOffsetChange(Math.max(0, offset - limit))}>
          <ChevronLeft aria-hidden="true" />
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label="Next page" disabled={last >= total} onClick={() => onOffsetChange(offset + limit)}>
          <ChevronRight aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
