import { ArrowDownRight, ArrowRight, ArrowUpRight, LoaderCircle } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

type MetricTrend = "up" | "down" | "flat";
type MetricTone = "neutral" | "success" | "warning" | "destructive";

/**
 * The signed period-over-period change, in the same chip vocabulary as every
 * other status on the page: a tinted surface behind a hairline of its own hue.
 */
const deltaPill: Record<MetricTone, string> = {
  neutral: "border-chip-neutral-edge bg-chip-neutral text-muted-foreground",
  success: "border-chip-success-edge bg-chip-success text-success",
  warning: "border-chip-warning-edge bg-chip-warning text-warning-ink",
  destructive: "border-chip-destructive-edge bg-chip-destructive text-destructive",
};

/**
 * One headline figure, in the shape a leader scans first: the label and its
 * mark on top, the number with its change pill beside it, and one quiet line
 * of context underneath. The pill renders only when a signed change actually
 * arrived — an absent comparison is never drawn as a fake flat zero.
 */
export function MetricCard({
  label,
  value,
  subline,
  delta,
  trend = "flat",
  tone = "neutral",
  loading = false,
  icon,
  className,
  ...props
}: React.ComponentProps<"article"> & {
  label: string;
  value: React.ReactNode;
  /** One quiet line of context under the figure, e.g. "vs. 12 last period". */
  subline?: string;
  /** Signed change against the comparable period, e.g. "+15%". */
  delta?: string | null;
  trend?: MetricTrend;
  tone?: MetricTone;
  loading?: boolean;
  /** Drawn top-right; pass `undefined` when no mark is approved for this figure. */
  icon?: React.ReactNode;
}) {
  const TrendIcon =
    trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : ArrowRight;
  return (
    <article
      aria-busy={loading || undefined}
      className={cn(
        "bg-card min-w-0 rounded-xl border px-5 py-4",
        loading && "text-muted-foreground",
        className,
      )}
      {...props}
    >
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 text-sm font-semibold tracking-[-0.01em]">{label}</p>
        {icon ? (
          <span className="text-primary shrink-0 [&_svg]:size-5" aria-hidden>
            {icon}
          </span>
        ) : null}
      </div>
      {loading ? (
        <div className="mt-3 flex h-9 items-center gap-2 text-sm">
          <LoaderCircle className="size-4 animate-spin" aria-hidden />
          Loading
        </div>
      ) : (
        <>
          <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <p className="text-metric font-bold tracking-[-0.02em] tabular-nums">
              {value}
            </p>
            {delta && delta !== "0%" ? (
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold tabular-nums",
                  deltaPill[tone],
                )}
              >
                <TrendIcon className="size-3" aria-hidden />
                {delta}
              </span>
            ) : null}
          </div>
          {subline ? (
            <p className="text-muted-foreground mt-1 truncate text-xs">{subline}</p>
          ) : null}
        </>
      )}
    </article>
  );
}

/**
 * A titled well holding two or more related metrics. The recessed background
 * is what makes the white metric surfaces inside it read as one comparison
 * rather than four unrelated cards in a row.
 */
export function MetricGroup({
  title,
  description,
  children,
  className,
  ...props
}: React.ComponentProps<"section"> & {
  title: string;
  description?: string;
}) {
  return (
    <section className={cn("bg-muted/40 rounded-2xl border p-2", className)} {...props}>
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 px-3 pt-2 pb-3">
        <h2 className="text-sm font-bold">{title}</h2>
        {description ? (
          <p className="text-muted-foreground text-xs">{description}</p>
        ) : null}
      </header>
      {/* Auto-fit rather than a fixed two-up: a group holding one figure
          should fill its well, not sit in half of it. */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-2">
        {children}
      </div>
    </section>
  );
}
