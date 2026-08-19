import { ArrowDownRight, ArrowRight, ArrowUpRight, LoaderCircle } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

type MetricTrend = "up" | "down" | "flat";
type MetricTone = "neutral" | "success" | "warning" | "destructive";

const trendTone: Record<MetricTone, string> = {
  neutral: "text-muted-foreground",
  success: "text-success",
  warning: "text-warning-ink",
  destructive: "text-destructive",
};

/**
 * One figure and the single fact that qualifies it. Carries its own surface so
 * it reads the same standing alone as it does inside a `MetricGroup`.
 */
export function MetricCard({
  label,
  value,
  hint,
  trend = "flat",
  tone = "neutral",
  loading = false,
  className,
  ...props
}: React.ComponentProps<"article"> & {
  label: string;
  value: React.ReactNode;
  hint?: string;
  trend?: MetricTrend;
  tone?: MetricTone;
  loading?: boolean;
}) {
  const TrendIcon =
    trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : ArrowRight;
  return (
    <article
      aria-busy={loading || undefined}
      className={cn(
        "bg-card min-w-0 rounded-lg border px-4 py-3.5",
        loading && "text-muted-foreground",
        className,
      )}
      {...props}
    >
      <p className="text-muted-foreground text-xs font-medium text-pretty">{label}</p>
      {loading ? (
        <div className="mt-2 flex h-8 items-center gap-2 text-sm">
          <LoaderCircle className="size-4 animate-spin" aria-hidden />
          Loading
        </div>
      ) : (
        <>
          <p className="mt-1.5 text-2xl leading-8 font-semibold tracking-[-0.02em] tabular-nums">
            {value}
          </p>
          {hint ? (
            <p className={cn("mt-1 flex gap-1 text-xs font-medium", trendTone[tone])}>
              <TrendIcon className="mt-px size-3.5 shrink-0 self-start" aria-hidden />
              <span>{hint}</span>
            </p>
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
    <section
      className={cn("bg-muted/45 rounded-xl border p-1.5", className)}
      {...props}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 px-2.5 pt-2 pb-2.5">
        <h2 className="text-sm font-semibold">{title}</h2>
        {description ? (
          <p className="text-muted-foreground text-xs">{description}</p>
        ) : null}
      </header>
      <div className="grid gap-1.5 sm:grid-cols-2">{children}</div>
    </section>
  );
}
