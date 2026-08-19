import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { MetricCards } from "@/components/dashboard/MetricCards";
import type { DashboardMetric, DashboardMetrics } from "@/types";

function metric(overrides: Partial<DashboardMetric> = {}): DashboardMetric {
  return {
    key: "teamNewAgents",
    label: "New agents",
    format: "count",
    scopeLevel: "office",
    definition: "Active users who joined in the trailing 30 days.",
    availability: "available",
    value: "4",
    hint: "Joined in the last 30 days",
    tone: "neutral",
    trend: "up",
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

describe("MetricCards", () => {
  it("renders the figures the server selected, grouped and scope-labelled", () => {
    render(<MetricCards metrics={payload()} />);

    expect(
      screen.getByRole("heading", { level: 2, name: "Team oversight" }),
    ).toBeVisible();
    expect(screen.getByText("New agents")).toBeVisible();
    expect(screen.getByText("4")).toBeVisible();
    // Team figures say what they cover; the cards do not repeat it.
    expect(screen.getByText("Fairfax VA")).toBeVisible();
  });

  it("links a card to the drill-down the server reversed", () => {
    render(<MetricCards metrics={payload()} />);

    const link = screen.getByRole("link", { name: "New agents — View new agents" });
    expect(link).toHaveAttribute("href", "/operations/new-agents");
  });

  it("marks an unconnected source as unavailable instead of showing a number", () => {
    render(
      <MetricCards
        metrics={payload({
          groups: [
            {
              key: "teamOperations",
              title: "Team operations",
              description: "Deals and resources in my scope",
              metrics: [
                metric({
                  key: "teamRoomUtilization",
                  label: "Room utilization",
                  format: "percent",
                  availability: "unavailable",
                  unavailableReason: "Reservations are not connected to the hub yet.",
                  value: null,
                  hint: "",
                  drillDown: null,
                }),
              ],
            },
          ],
        })}
      />,
    );

    expect(screen.getByText("—")).toBeVisible();
    expect(
      screen.getByText("Reservations are not connected to the hub yet."),
    ).toBeVisible();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("renders nothing when the user is entitled to no metrics", () => {
    const { container } = render(<MetricCards metrics={payload({ groups: [] })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<MetricCards metrics={payload()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
