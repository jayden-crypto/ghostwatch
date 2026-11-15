"use client";

/**
 * A collapsible, syntax-coloured view of any JSON value, with copy buttons.
 *
 * It shows what was stored and nothing else. A payload the backend truncated (contract §0) gets an
 * explicit banner with its original size, and its preview is shown as raw text because it is the
 * first 2,000 characters of a document, not a document.
 */
import { ChevronRight, Scissors } from "lucide-react";
import { useState } from "react";

import type { Json } from "@/lib/api/types";
import { formatBytes, formatCount } from "@/lib/format";
import { isJsonObject, isTruncatedPayload } from "@/lib/json";
import { cn } from "@/lib/utils";

import { CopyButton } from "./values";

/** Entries of one object or array shown before "Show more". Keeps a 64 KB payload from freezing the page. */
const PAGE = 100;
/** Characters of one string shown before "Show all". */
const STRING_LIMIT = 400;

const INDENT = 14;

function Primitive({ value }: { value: null | boolean | number | string }) {
  const [open, setOpen] = useState(false);
  if (value === null) return <span className="text-json-keyword">null</span>;
  if (typeof value === "boolean") return <span className="text-json-keyword">{String(value)}</span>;
  if (typeof value === "number") return <span className="text-json-number">{String(value)}</span>;
  const long = value.length > STRING_LIMIT;
  const shown = long && !open ? value.slice(0, STRING_LIMIT) : value;
  return (
    <>
      <span className="whitespace-pre-wrap break-words text-json-string">
        {JSON.stringify(shown).slice(0, long && !open ? -1 : undefined)}
        {long && !open && "…"}
      </span>
      {long && (
        <button type="button" onClick={() => setOpen(!open)} className="ml-2 rounded-sm text-fg-subtle underline underline-offset-2 hover:text-fg">
          {open ? "Show less" : `Show all ${formatCount(value.length)} characters`}
        </button>
      )}
    </>
  );
}

function Node({ name, value, depth, expandDepth, last }: { name?: string; value: Json; depth: number; expandDepth: number; last: boolean }) {
  const container = Array.isArray(value) || isJsonObject(value);
  const entries: [string | undefined, Json][] = Array.isArray(value)
    ? value.map((item) => [undefined, item])
    : isJsonObject(value)
      ? Object.entries(value)
      : [];
  const [open, setOpen] = useState(depth < expandDepth);
  const [shown, setShown] = useState(PAGE);
  const key = name !== undefined && (
    <>
      <span className="text-fg-muted">{JSON.stringify(name)}</span>
      <span className="text-fg-subtle">: </span>
    </>
  );
  const comma = !last && <span className="text-fg-subtle">,</span>;

  if (!container) {
    return (
      <div style={{ paddingLeft: depth * INDENT + 14 }}>
        {key}
        <Primitive value={value as null | boolean | number | string} />
        {comma}
      </div>
    );
  }

  const [openBracket, closeBracket] = Array.isArray(value) ? ["[", "]"] : ["{", "}"];
  if (entries.length === 0) {
    return (
      <div style={{ paddingLeft: depth * INDENT + 14 }}>
        {key}
        <span className="text-fg-subtle">
          {openBracket}
          {closeBracket}
        </span>
        {comma}
      </div>
    );
  }

  const summary = Array.isArray(value)
    ? `${formatCount(entries.length)} ${entries.length === 1 ? "item" : "items"}`
    : `${formatCount(entries.length)} ${entries.length === 1 ? "key" : "keys"}`;
  return (
    <div>
      <div className="group/node flex items-start" style={{ paddingLeft: depth * INDENT }}>
        <button
          type="button"
          aria-expanded={open}
          aria-label={`${open ? "Collapse" : "Expand"} ${name ?? "value"}`}
          onClick={() => setOpen(!open)}
          className="mt-0.5 flex size-3.5 shrink-0 items-center justify-center rounded-sm text-fg-subtle hover:bg-hover hover:text-fg"
        >
          <ChevronRight className={cn("size-3 transition-transform duration-150 ease-out", open && "rotate-90")} aria-hidden="true" />
        </button>
        <span>
          {key}
          <span className="text-fg-subtle">{openBracket}</span>
          {!open && (
            <>
              <button type="button" onClick={() => setOpen(true)} className="mx-1 rounded-sm text-fg-subtle hover:text-fg">
                {summary}
              </button>
              <span className="text-fg-subtle">{closeBracket}</span>
              {comma}
            </>
          )}
        </span>
        <CopyButton
          value={JSON.stringify(value, null, 2)}
          label={name ? `"${name}" as JSON` : "JSON"}
          className="ml-1 size-4 opacity-0 focus-visible:opacity-100 group-hover/node:opacity-100"
        />
      </div>
      {open && (
        <>
          {entries.slice(0, shown).map(([childName, child], index) => (
            <Node
              key={childName ?? index}
              name={childName}
              value={child}
              depth={depth + 1}
              expandDepth={expandDepth}
              last={index === entries.length - 1}
            />
          ))}
          {entries.length > shown && (
            <div style={{ paddingLeft: (depth + 1) * INDENT + 14 }}>
              <button type="button" onClick={() => setShown(shown + PAGE)} className="rounded-sm text-fg-subtle underline underline-offset-2 hover:text-fg">
                Show {formatCount(Math.min(PAGE, entries.length - shown))} more of {formatCount(entries.length - shown)} remaining
              </button>
            </div>
          )}
          <div style={{ paddingLeft: depth * INDENT + 14 }}>
            <span className="text-fg-subtle">{closeBracket}</span>
            {comma}
          </div>
        </>
      )}
    </div>
  );
}

export function JsonViewer({
  value,
  expandDepth = 2,
  className,
  label = "JSON",
}: {
  value: Json;
  /** Levels open at first. */
  expandDepth?: number;
  className?: string;
  /** What the top copy button says it copies. */
  label?: string;
}) {
  if (isTruncatedPayload(value)) {
    return (
      <div className={cn("overflow-hidden rounded-md border border-timed-out/40", className)}>
        <div role="note" className="flex items-start gap-2 border-b border-timed-out/40 bg-timed-out/10 px-3 py-2">
          <Scissors className="mt-0.5 size-3.5 shrink-0 text-timed-out" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="font-medium text-timed-out">Payload truncated — {formatBytes(value.original_bytes)}</p>
            <p className="text-fg-muted">
              This payload was {formatCount(value.original_bytes)} bytes, over the 64 KB limit. Only its first{" "}
              {formatCount(value.preview.length)} characters were stored; the rest cannot be recovered.
            </p>
          </div>
          <CopyButton value={value.preview} label="the stored preview" />
        </div>
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all bg-surface p-3 font-mono text-xs leading-5 text-fg-muted">
          {value.preview}
          <span className="text-fg-subtle"> …</span>
        </pre>
      </div>
    );
  }
  return (
    <div className={cn("relative rounded-md border border-line-subtle bg-surface p-3 pr-9 font-mono text-xs leading-5", className)}>
      <CopyButton value={JSON.stringify(value, null, 2)} label={label} className="absolute right-2 top-2" />
      <Node value={value} depth={0} expandDepth={expandDepth} last />
    </div>
  );
}
