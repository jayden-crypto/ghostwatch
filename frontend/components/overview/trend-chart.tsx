"use client";

/**
 * Executions over time, stacked by how they ended. One bar per bucket of `/stats/timeseries`;
 * empty buckets arrive from the API as zeros, so the chart never has gaps to paper over.
 */
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { StatsBucket, StatsTimeseries, TimeseriesPoint } from "@/lib/api/types";
import { formatCount, formatDuration } from "@/lib/format";

const SERIES = [
  { key: "completed", label: "Completed", color: "var(--completed)" },
  { key: "failed", label: "Failed", color: "var(--failed)" },
  { key: "timed_out", label: "Timed out", color: "var(--timed-out)" },
] as const;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** `17:00` for hour buckets, `Nov 14` for day buckets. Buckets are UTC, so the labels are too. */
export function bucketLabel(bucketStart: string, bucket: StatsBucket): string {
  const date = new Date(bucketStart);
  return bucket === "hour"
    ? `${String(date.getUTCHours()).padStart(2, "0")}:00`
    : `${MONTHS[date.getUTCMonth()]} ${date.getUTCDate()}`;
}

const total = (point: TimeseriesPoint) => point.completed + point.failed + point.timed_out;

/** `point` is the bucket under the pointer: the row of API data the hovered bar was drawn from. */
function BucketTooltip({ point, bucket }: { point: TimeseriesPoint | undefined; bucket: StatsBucket }) {
  if (!point) return null;
  const date = new Date(point.bucket_start);
  const heading =
    bucket === "hour"
      ? `${MONTHS[date.getUTCMonth()]} ${date.getUTCDate()}, ${bucketLabel(point.bucket_start, "hour")} UTC`
      : `${MONTHS[date.getUTCMonth()]} ${date.getUTCDate()}, ${date.getUTCFullYear()} (UTC)`;
  return (
    <div className="rounded-md border border-line bg-raised px-3 py-2 text-xs shadow-lg">
      <p className="mb-1.5 font-medium">{heading}</p>
      <dl className="flex flex-col gap-1">
        {SERIES.map((series) => (
          <div key={series.key} className="flex items-center justify-between gap-6">
            <dt className="flex items-center gap-1.5 text-fg-muted">
              <span aria-hidden="true" className="size-2 rounded-[2px]" style={{ background: series.color }} />
              {series.label}
            </dt>
            <dd className="num font-mono">{formatCount(point[series.key])}</dd>
          </div>
        ))}
        <div className="mt-1 flex items-center justify-between gap-6 border-t border-line pt-1.5">
          <dt className="text-fg-muted">Avg duration</dt>
          <dd className="num font-mono">{formatDuration(point.avg_duration_ms)}</dd>
        </div>
      </dl>
    </div>
  );
}

export function TrendChart({ data }: { data: StatsTimeseries }) {
  const finished = data.points.reduce((sum, point) => sum + total(point), 0);
  const peak = data.points.reduce((best, point) => (total(point) > total(best) ? point : best), data.points[0]);
  const summary =
    finished === 0
      ? `No executions finished in this window.`
      : `${formatCount(finished)} executions finished in this window. Busiest ${data.bucket}: ${bucketLabel(peak.bucket_start, data.bucket)} with ${formatCount(total(peak))}.`;

  return (
    <figure className="flex h-full flex-col gap-3">
      <figcaption className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-muted">
        {SERIES.map((series) => (
          <span key={series.key} className="flex items-center gap-1.5">
            <span aria-hidden="true" className="size-2 rounded-[2px]" style={{ background: series.color }} />
            {series.label}
          </span>
        ))}
        <span className="ml-auto text-fg-subtle">
          per {data.bucket}, UTC · by start time
        </span>
      </figcaption>
      <div className="relative min-h-0 flex-1" role="img" aria-label={`Executions per ${data.bucket}, stacked by outcome. ${summary}`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data.points} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap="22%">
            <CartesianGrid vertical={false} stroke="var(--line-subtle)" />
            <XAxis
              dataKey="bucket_start"
              tickFormatter={(value: string) => bucketLabel(value, data.bucket)}
              tick={{ fill: "var(--fg-subtle)", fontSize: 11, fontFamily: "var(--font-geist-mono)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--line)" }}
              minTickGap={24}
              interval="preserveStartEnd"
            />
            <YAxis
              allowDecimals={false}
              width={32}
              tick={{ fill: "var(--fg-subtle)", fontSize: 11, fontFamily: "var(--font-geist-mono)" }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              cursor={{ fill: "var(--raised)" }}
              isAnimationActive={false}
              content={({ active, payload }) => (
                <BucketTooltip point={active ? (payload?.[0]?.payload as TimeseriesPoint | undefined) : undefined} bucket={data.bucket} />
              )}
            />
            {SERIES.map((series) => (
              <Bar key={series.key} dataKey={series.key} name={series.label} stackId="outcome" fill={series.color} isAnimationActive={false} maxBarSize={36} />
            ))}
          </BarChart>
        </ResponsiveContainer>
        {finished === 0 && (
          <p className="absolute inset-0 flex items-center justify-center text-fg-muted">No executions finished in this window.</p>
        )}
      </div>
    </figure>
  );
}
