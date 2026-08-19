import { Link } from "@inertiajs/react";

import { MetricCard, MetricGroup } from "@/components/design-system/metric-card";
import type { DashboardMetric, DashboardMetrics } from "@/types";

/**
 * The dashboard's headline figures.
 *
 * Which cards appear, what they count, and where they link is decided by the
 * registry in `apps/web/metrics.py` from the signed-in user's effective
 * permissions and scope. This component renders the arriving payload and makes
 * no entitlement decision of its own — every drill-down it offers is guarded by
 * the same permission on the server.
 */

/** Placeholder for a figure that has no data source yet. */
const NO_VALUE = "—";

function Metric({ metric }: { metric: DashboardMetric }) {
  const unavailable = metric.availability === "unavailable";
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

export function MetricCards({ metrics }: { metrics: DashboardMetrics }) {
  if (metrics.groups.length === 0) {
    return null;
  }
  return (
    <div className="arrive grid gap-4 xl:grid-cols-2">
      {metrics.groups.map((group) => (
        <MetricGroup
          key={group.key}
          title={group.title}
          // Team figures are ambiguous without the scope they cover, so the
          // group says it once rather than every card repeating it.
          description={
            group.key.startsWith("team") ? metrics.scope.label : group.description
          }
        >
          {group.metrics.map((metric) => (
            <Metric key={metric.key} metric={metric} />
          ))}
        </MetricGroup>
      ))}
    </div>
  );
}

export function MetricCardsSkeleton() {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {["first", "second"].map((group) => (
        <MetricGroup key={group} title="Loading metrics">
          <MetricCard label="Loading" value={NO_VALUE} loading />
          <MetricCard label="Loading" value={NO_VALUE} loading />
        </MetricGroup>
      ))}
    </div>
  );
}
