import { Link } from "@inertiajs/react";
import { format } from "date-fns";
import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { MetricCard, MetricGroup } from "@/components/design-system/metric-card";
import { Button } from "@/components/ui/button";
import type { DashboardMetric, DashboardMetricGroup, DashboardMetrics } from "@/types";

/**
 * The dashboard's headline figures.
 *
 * Which cards a reader is entitled to is decided by the registry in
 * `apps/web/metrics.py` from their effective permissions and scope. This
 * component renders the arriving payload and makes no entitlement decision of
 * its own — every drill-down it offers is guarded by the same permission on
 * the server.
 *
 * What it does decide is *emphasis*. A brokerage-wide leader is entitled to a
 * dozen figures and most of them have no data source yet, which turns the top
 * of their dashboard into a grid of dashes. Unmeasured figures are folded away
 * behind one line, so what is left above the fold is the numbers that exist.
 * Nothing is dropped: the fold opens.
 */

/** Placeholder for a figure that has no data source yet. */
const NO_VALUE = "—";

function isMeasured(metric: DashboardMetric): boolean {
  return metric.availability === "available";
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

function Metric({ metric }: { metric: DashboardMetric }) {
  const unavailable = !isMeasured(metric);
  const card = (
    <MetricCard
      className={
        metric.drillDown
          ? "group-hover:border-ring/40 h-full transition-colors"
          : "h-full"
      }
      label={metric.label}
      value={unavailable ? NO_VALUE : (metric.value ?? NO_VALUE)}
      hint={unavailable ? metric.unavailableReason : metric.hint}
      trend={unavailable ? "flat" : metric.trend}
      tone={unavailable ? "neutral" : metric.tone}
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
      className="focus-visible:ring-ring focus-visible:ring-offset-background group rounded-lg focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      {card}
    </Link>
  );
}

function Group({
  group,
  metrics,
  scopeLabel,
}: {
  group: DashboardMetricGroup;
  metrics: DashboardMetric[];
  scopeLabel: string;
}) {
  return (
    <MetricGroup
      title={group.title}
      // Team figures are ambiguous without the scope they cover, so the group
      // says it once rather than every card repeating it.
      description={group.key.startsWith("team") ? scopeLabel : group.description}
    >
      {metrics.map((metric) => (
        <Metric key={metric.key} metric={metric} />
      ))}
    </MetricGroup>
  );
}

export function MetricCards({ metrics }: { metrics: DashboardMetrics }) {
  const [expanded, setExpanded] = useState(false);

  if (metrics.groups.length === 0) {
    return null;
  }

  const unmeasuredCount = metrics.groups.reduce(
    (total, group) => total + group.metrics.filter((m) => !isMeasured(m)).length,
    0,
  );
  const visible = metrics.groups
    .map((group) => ({
      group,
      metrics: expanded ? group.metrics : group.metrics.filter(isMeasured),
    }))
    .filter((entry) => entry.metrics.length > 0);

  const asOf = sectionAsOf(metrics);
  const asOfLabel = asOf ? formatAsOf(asOf) : "";

  const toggle =
    unmeasuredCount === 0 ? null : (
      <Button
        variant="ghost"
        size="sm"
        className="text-muted-foreground -ms-2 h-auto min-h-9 max-w-full w-fit justify-start whitespace-normal py-2 text-left leading-5"
        aria-expanded={expanded}
        onClick={() => setExpanded((open) => !open)}
      >
        <ChevronDown
          className={
            expanded ? "rotate-180 transition-transform" : "transition-transform"
          }
          aria-hidden
        />
        {expanded
          ? "Hide figures without a data source"
          : `Show ${unmeasuredCount} ${unmeasuredCount === 1 ? "figure" : "figures"} without a data source yet`}
      </Button>
    );

  return (
    <div className="arrive @container grid gap-3">
      {visible.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 @3xl:grid-cols-2">
          {visible.map((entry) => (
            <Group
              key={entry.group.key}
              group={entry.group}
              metrics={entry.metrics}
              scopeLabel={metrics.scope.label}
            />
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">
          None of your figures have a data source yet.
        </p>
      )}
      {asOfLabel ? (
        <p className="text-muted-foreground text-xs">As of {asOfLabel}</p>
      ) : null}
      {toggle}
    </div>
  );
}

export function MetricCardsSkeleton() {
  return (
    <div className="@container grid gap-4">
      <div className="grid grid-cols-1 gap-4 @3xl:grid-cols-2">
        {["first", "second"].map((group) => (
          <MetricGroup key={group} title="Loading metrics">
            <MetricCard label="Loading" value={NO_VALUE} loading />
            <MetricCard label="Loading" value={NO_VALUE} loading />
          </MetricGroup>
        ))}
      </div>
    </div>
  );
}
