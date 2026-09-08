import { Link } from "@inertiajs/react";
import { format } from "date-fns";

import { MetricCard, MetricStrip } from "@/components/design-system/metric-card";
import { metricIcon } from "@/lib/metric-icons";
import { cn } from "@/lib/utils";
import type { DashboardMetric, DashboardMetrics } from "@/types";

/**
 * The dashboard's headline figures — one responsive row of stat cards.
 *
 * Which cards a reader is entitled to is decided by the registry in
 * `apps/web/metrics.py` from their effective permissions and scope. This
 * component renders the arriving payload and makes no entitlement decision of
 * its own — every drill-down it offers is guarded by the same permission on
 * the server.
 *
 * Only figures that actually have a data source are rendered. A metric whose
 * source module is not connected yet is not a number the reader can act on, so
 * it is left out rather than counted, promised, or shown as a placeholder.
 */

/** Placeholder for a figure that is still loading. */
const NO_VALUE = "—";

function isMeasured(metric: DashboardMetric): boolean {
  return metric.availability === "available";
}

function flatten(metrics: DashboardMetrics): DashboardMetric[] {
  return metrics.groups.flatMap((group) => group.metrics);
}

function sectionAsOf(metrics: DashboardMetrics): string | null {
  for (const group of metrics.groups) {
    for (const metric of group.metrics) {
      if (metric.asOf) {
        return metric.asOf;
      }
    }
  }
  return null;
}

function formatAsOf(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return format(date, "PPP p");
}

/** "vs. 12 last period" when a comparison arrived; otherwise the hint. */
function sublineFor(metric: DashboardMetric): string | undefined {
  if (!isMeasured(metric)) {
    return metric.unavailableReason;
  }
  if (metric.comparedTo != null && metric.comparedTo !== "") {
    return `vs. ${metric.comparedTo} last period`;
  }
  return metric.hint || undefined;
}

function StatCard({ metric }: { metric: DashboardMetric }) {
  const unavailable = !isMeasured(metric);
  const Icon = metricIcon(metric.icon);
  const card = (
    <MetricCard
      className={cn(
        "h-full",
        // A figure that drills through lifts on hover the way a table row
        // does: a wash, not a border change — a colour-shifting rule inside a
        // ruled strip makes the whole grid look like it moved.
        metric.drillDown &&
          "group-hover:bg-accent/45 transition-colors duration-(--motion-fast)",
      )}
      label={metric.label}
      value={unavailable ? NO_VALUE : (metric.value ?? NO_VALUE)}
      subline={sublineFor(metric)}
      delta={unavailable ? null : (metric.delta ?? null)}
      trend={unavailable ? "flat" : metric.trend}
      tone={unavailable ? "neutral" : metric.tone}
      icon={<Icon />}
      // The calculation definition travels with the figure so a leader can
      // check what a number means without leaving the page.
      title={metric.definition}
      aria-label={
        unavailable
          ? `${metric.label}: ${metric.unavailableReason ?? "not available"}`
          : undefined
      }
    />
  );

  if (!metric.drillDown) {
    return card;
  }
  return (
    <Link
      href={metric.drillDown.href}
      aria-label={`${metric.label} — ${metric.drillDown.label}`}
      className="focus-visible:outline-ring group block h-full min-w-0 focus-visible:outline-2 focus-visible:-outline-offset-2"
    >
      {card}
    </Link>
  );
}

export function MetricCards({ metrics }: { metrics: DashboardMetrics }) {
  if (metrics.groups.length === 0) {
    return null;
  }

  const visible = flatten(metrics).filter(isMeasured);
  const asOf = sectionAsOf(metrics);
  const asOfLabel = asOf ? formatAsOf(asOf) : "";
  // Team figures are ambiguous without the scope they cover, so the row says
  // it once rather than every card repeating it. A self-scoped book of
  // business needs no caption: it covers exactly one person, obviously.
  const scopeCaption =
    metrics.scope.level === "self" ? null : `Team figures cover ${metrics.scope.label}`;

  return (
    <div className="arrive @container grid gap-3">
      {visible.length > 0 ? (
        // One strip, auto-fitting: these figures are permission- and
        // source-filtered, so the count varies per reader, and a ruled row
        // absorbs three figures or seven without the gaps a fixed grid leaves.
        <MetricStrip>
          {visible.map((metric) => (
            <StatCard key={metric.key} metric={metric} />
          ))}
        </MetricStrip>
      ) : (
        <p className="text-muted-foreground text-sm">
          None of your figures have a data source yet.
        </p>
      )}
      {/* One footnote to the band, not a stack of stranded lines under it. */}
      {scopeCaption || asOfLabel ? (
        <p className="text-muted-foreground text-xs">
          {[scopeCaption, asOfLabel ? `As of ${asOfLabel}` : null]
            .filter(Boolean)
            .join(" · ")}
        </p>
      ) : null}
    </div>
  );
}

export function MetricCardsSkeleton() {
  return (
    <div className="@container grid gap-3">
      <MetricStrip>
        {["first", "second", "third", "fourth"].map((slot) => (
          <MetricCard key={slot} label="Loading" value={NO_VALUE} loading />
        ))}
      </MetricStrip>
    </div>
  );
}
