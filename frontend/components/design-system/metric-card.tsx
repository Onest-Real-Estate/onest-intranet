import { ArrowDownRight, ArrowRight, ArrowUpRight, LoaderCircle } from "lucide-react";
import * as React from "react";

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
 * One headline figure.
 *
 * The label leads in the same 12px caps a table column header uses, the figure
 * sits under it at the metric step, and the change chip rides the figure's
 * baseline. Reading order matches scanning order: a leader looks for *which*
 * number before *what* it says.
 *
 * `frame` defaults to `"cell"`: no border and no radius of its own, because a
 * figure almost always appears in a row of figures and `MetricStrip` draws the
 * rules between them. `frame="card"` re-adds the border for the rare figure
 * that genuinely stands alone.
 */
export function MetricCard({
  label,
  value,
  subline,
  delta,
  trend = "flat",
  tone = "neutral",
  loading = false,
  frame = "cell",
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
  /** `cell` inside a `MetricStrip`; `card` when the figure stands alone. */
  frame?: "card" | "cell";
  /** Drawn beside the label; pass `undefined` when no mark is approved. */
  icon?: React.ReactNode;
}) {
  const TrendIcon =
    trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : ArrowRight;
  return (
    <article
      aria-busy={loading || undefined}
      className={cn(
        "bg-card min-w-0 px-5 py-4",
        frame === "card" && "rounded-(--radius-card) border",
        loading && "text-muted-foreground",
        className,
      )}
      {...props}
    >
      {/* The mark sits *with* the label rather than opposite it. Parked in the
          far corner it reads as a button and pulls the eye away from the
          figure, which is the only thing on the tile worth looking at. */}
      <p className="text-muted-foreground flex min-w-0 items-center gap-1.5 text-xs font-semibold tracking-[0.06em] uppercase">
        {icon ? (
          <span className="shrink-0 [&_svg]:size-3.5" aria-hidden>
            {icon}
          </span>
        ) : null}
        <span className="min-w-0 truncate">{label}</span>
      </p>
      {loading ? (
        <div className="mt-2 flex h-9 items-center gap-2 text-sm">
          <LoaderCircle className="size-4 animate-spin" aria-hidden />
          Loading
        </div>
      ) : (
        <>
          <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <p className="text-metric text-foreground font-bold tracking-[-0.02em] tabular-nums">
              {value}
            </p>
            {delta && delta !== "0%" ? (
              <span
                className={cn(
                  "inline-flex translate-y-px items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-semibold tabular-nums",
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
 * A row of figures read as one instrument, not as a shelf of separate cards.
 *
 * The strip is a single surface divided by hairlines: the same rules that run
 * between the columns of a table, turned on a row of numbers. Four bordered
 * cards float four ways and invite the eye to compare their *edges*; one ruled
 * panel puts the figures on a common baseline, which is what makes them
 * comparable at a glance — and it is one object on the page instead of four.
 *
 * Cells auto-fit, so the same strip is four across on a monitor and one across
 * on a phone with no breakpoint anywhere. Each cell draws its own top and left
 * rule and the grid is pulled a pixel into the frame, so the outermost rules
 * land underneath the panel border rather than doubling it.
 */
export function MetricStrip({
  min = "13rem",
  max = "22rem",
  className,
  children,
  ...props
}: React.ComponentProps<"div"> & {
  /** Narrowest a cell may get before the row rewraps. */
  min?: string;
  /** Widest a single cell may grow. Caps the strip, not the cells. */
  max?: string;
}) {
  // The strip is capped at what its own cells can fill. Auto-fit alone would
  // stretch a lone figure across the whole band, putting its label and its
  // number a screen apart and turning one fact into a billboard — so the frame
  // stops where the figures do. At four across the cap clears any real page
  // width, so a full row still runs edge to edge.
  const cells = React.Children.count(children);

  return (
    <div
      className={cn(
        "bg-card rounded-(--radius-card) border",
        // The clip is what makes the technique work: it crops the pixel the
        // grid is pulled by, so the outermost cell rules land outside the
        // padding box and the frame's own border is the only line there.
        "overflow-hidden",
        className,
      )}
      style={{ maxWidth: `calc(${cells} * ${max})` }}
      {...props}
    >
      <div
        className="-m-px grid [&>*]:border-t [&>*]:border-l [&>*]:border-border"
        style={{
          gridTemplateColumns: `repeat(auto-fit, minmax(${min}, 1fr))`,
        }}
      >
        {children}
      </div>
    </div>
  );
}

/**
 * A titled well holding two or more related metrics. The heading is what makes
 * the strip under it read as one comparison rather than a second unrelated row
 * of numbers.
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
    <section className={cn("grid content-start gap-2", className)} {...props}>
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <h2 className="text-sm font-semibold">{title}</h2>
        {description ? (
          <p className="text-muted-foreground text-xs">{description}</p>
        ) : null}
      </header>
      <MetricStrip min="11rem">{children}</MetricStrip>
    </section>
  );
}
