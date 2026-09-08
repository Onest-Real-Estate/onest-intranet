import { render, screen } from "@testing-library/react";
import { format } from "date-fns";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { MetricCards } from "@/components/dashboard/MetricCards";
import type { DashboardMetric, DashboardMetrics } from "@/types";

const AS_OF = "2026-08-19T09:00:00-04:00";

function metric(overrides: Partial<DashboardMetric> = {}): DashboardMetric {
  return {
    key: "teamNewAgents",
    label: "New agents",
    format: "count",
    scopeLevel: "office",
    definition: "Active users who joined in the trailing 30 days.",
    asOf: AS_OF,
    availability: "available",
    value: "4",
    rawValue: 4,
    unit: "count",
    hint: "Joined in the last 30 days",
    tone: "neutral",
    trend: "up",
    icon: "new-agents",
    drillDown: { href: "/operations/new-agents", label: "View new agents" },
    ...overrides,
  };
}

function payload(overrides: Partial<DashboardMetrics> = {}): DashboardMetrics {
  return {
    scope: { level: "office", label: "Fairfax VA" },
    groups: [
      {
        key: "teamOversight",
        title: "Team oversight",
        description: "People and compliance in my scope",
        metrics: [metric()],
      },
    ],
    ...overrides,
  };
}

function unmeasuredGroup() {
  return {
    key: "teamOperations",
    title: "Team operations",
    description: "Deals and resources in my scope",
    metrics: [
      metric({
        key: "teamRoomUtilization",
        label: "Room utilization",
        format: "percent" as const,
        availability: "unavailable" as const,
        unavailableReason: "Reservations are not connected to the hub yet.",
        value: null,
        rawValue: undefined,
        unit: undefined,
        hint: "",
        drillDown: null,
      }),
    ],
  };
}

/** One measured figure and one that has no source yet. */
function mixed(): DashboardMetrics {
  const base = payload();
  return { ...base, groups: [...base.groups, unmeasuredGroup()] };
}

describe("MetricCards", () => {
  it("renders the figures the server selected as a flat stat row", () => {
    render(<MetricCards metrics={payload()} />);

    expect(screen.getByText("New agents")).toBeVisible();
    expect(screen.getByText("4")).toBeVisible();
    // Team figures say what they cover once — the cards do not repeat it.
    expect(screen.getByText(/Team figures cover Fairfax VA/)).toBeVisible();
  });

  it("shows section freshness from the metric as-of timestamp", () => {
    render(<MetricCards metrics={payload()} />);
    // Scope and freshness share one footnote line, so match within it.
    expect(
      screen.getByText(new RegExp(`As of ${format(new Date(AS_OF), "PPP p")}`)),
    ).toBeVisible();
  });

  it("omits the scope caption for a self-scoped book of business", () => {
    render(
      <MetricCards
        metrics={payload({
          scope: { level: "self", label: "My book of business" },
        })}
      />,
    );
    expect(screen.queryByText(/Team figures cover/)).toBeNull();
  });

  it("links a card to the drill-down the server reversed", () => {
    render(<MetricCards metrics={payload()} />);

    const link = screen.getByRole("link", { name: "New agents — View new agents" });
    expect(link).toHaveAttribute("href", "/operations/new-agents");
  });

  it("renders an arrived period-over-period delta as a signed pill", () => {
    const base = payload();
    const group = base.groups.at(0);
    if (!group) {
      throw new Error("the fixture payload has no group");
    }
    const first = group.metrics.at(0);
    if (!first) {
      throw new Error("the fixture group has no metric");
    }
    const { unmount } = render(<MetricCards metrics={base} />);
    // trend "up" alone renders no pill — the pill needs a real delta.
    expect(screen.queryByText("+50%")).toBeNull();
    unmount();

    render(
      <MetricCards
        metrics={{
          ...base,
          groups: [
            {
              ...group,
              metrics: [
                {
                  ...first,
                  delta: "+33%",
                  comparedTo: "3",
                  tone: "success" as const,
                },
              ],
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("+33%")).toBeVisible();
    expect(screen.getByText("vs. 3 last period")).toBeVisible();
  });

  it("keeps a measured zero distinct from a figure with no source", () => {
    render(
      <MetricCards
        metrics={payload({
          groups: [
            {
              key: "teamOversight",
              title: "Team oversight",
              description: "People and compliance in my scope",
              metrics: [
                metric({
                  key: "teamNewAgents",
                  value: "0",
                  rawValue: 0,
                  trend: "flat",
                  drillDown: null,
                }),
                metric({
                  key: "teamComplianceExceptions",
                  label: "Compliance exceptions",
                  availability: "unavailable",
                  unavailableReason:
                    "Compliance tracking is not connected to the hub yet.",
                  value: null,
                  hint: "",
                  icon: "compliance",
                  drillDown: null,
                }),
              ],
            },
          ],
        })}
      />,
    );

    // A measured zero is a real answer and is shown as one.
    expect(screen.getByText("0")).toBeVisible();
    // A figure with no data source is not an answer, so it is not rendered at
    // all — not as a dash, and not behind a disclosure either.
    expect(screen.queryByText("Compliance exceptions")).toBeNull();
    expect(screen.queryByText("—")).toBeNull();
    expect(
      screen.queryByText("Compliance tracking is not connected to the hub yet."),
    ).toBeNull();
  });

  it("lays out up to four measured figures without dropping any", () => {
    render(
      <MetricCards
        metrics={payload({
          groups: [
            {
              key: "myPipeline",
              title: "My pipeline",
              description: "Deals I own",
              metrics: [
                metric({ key: "a", label: "Active", value: "1", drillDown: null }),
                metric({ key: "b", label: "Closings", value: "2", drillDown: null }),
                metric({
                  key: "c",
                  label: "Commission",
                  value: "$3.00",
                  format: "currency",
                  drillDown: null,
                }),
                metric({
                  key: "d",
                  label: "Pending tasks",
                  value: "5",
                  drillDown: null,
                }),
              ],
            },
          ],
        })}
      />,
    );

    expect(screen.getByText("Active")).toBeVisible();
    expect(screen.getByText("Closings")).toBeVisible();
    expect(screen.getByText("Commission")).toBeVisible();
    expect(screen.getByText("Pending tasks")).toBeVisible();
    expect(screen.getByText("$3.00")).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders every measured figure, however many there are", () => {
    render(
      <MetricCards
        metrics={payload({
          groups: [
            {
              key: "myWork",
              title: "My work",
              description: "What is on me this week",
              metrics: [
                metric({ key: "a", label: "Active", value: "1", drillDown: null }),
                metric({ key: "b", label: "Closings", value: "2", drillDown: null }),
                metric({ key: "c", label: "Leads", value: "3", drillDown: null }),
                metric({ key: "d", label: "Tasks", value: "4", drillDown: null }),
                metric({ key: "e", label: "Open tasks", value: "7", drillDown: null }),
                metric({
                  key: "f",
                  label: "Follow-ups due",
                  value: "2",
                  drillDown: null,
                }),
              ],
            },
          ],
        })}
      />,
    );

    for (const label of [
      "Active",
      "Closings",
      "Leads",
      "Tasks",
      "Open tasks",
      "Follow-ups due",
    ]) {
      expect(screen.getByText(label)).toBeVisible();
    }
    // Nothing is hidden behind a disclosure, so there is nothing to expand.
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("leaves a figure with no data source out entirely", () => {
    // A brokerage-wide leader is entitled to a dozen figures and most have no
    // source yet. They are not counted, promised, or shown as dashes — the row
    // is the numbers that exist and nothing else.
    render(<MetricCards metrics={mixed()} />);

    expect(screen.getByText("New agents")).toBeVisible();
    expect(screen.queryByText("Room utilization")).toBeNull();
    expect(
      screen.queryByText("Reservations are not connected to the hub yet."),
    ).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("offers a drill-down only for the figures it renders", () => {
    render(<MetricCards metrics={mixed()} />);

    // One measured figure, one link. The unmeasured figure contributes
    // neither a card nor a destination.
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("says so plainly when nothing the reader is entitled to has a source", () => {
    render(<MetricCards metrics={payload({ groups: [unmeasuredGroup()] })} />);

    expect(
      screen.getByText("None of your figures have a data source yet."),
    ).toBeVisible();
    expect(screen.queryByText("Room utilization")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders nothing when the user is entitled to no metrics", () => {
    const { container } = render(<MetricCards metrics={payload({ groups: [] })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("has no detectable accessibility violations for measured cards", async () => {
    const { container } = render(<MetricCards metrics={payload()} />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("has no detectable accessibility violations for a mixed entitlement", async () => {
    const { container } = render(<MetricCards metrics={mixed()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
