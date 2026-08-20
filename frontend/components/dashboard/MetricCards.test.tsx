import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("folds figures that have no data source out of the way", async () => {
    // A brokerage-wide leader is entitled to a dozen figures, most of which
    // have no source yet. Showing them all turns the top of the page into a
    // grid of dashes and pushes the real numbers below the fold.
    render(<MetricCards metrics={mixed()} />);

    expect(screen.getByText("New agents")).toBeVisible();
    expect(screen.queryByText("Room utilization")).toBeNull();

    const toggle = screen.getByRole("button", {
      name: "Show 1 figure without a data source yet",
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(toggle);

    expect(screen.getByText("Room utilization")).toBeVisible();
    expect(
      screen.getByText("Reservations are not connected to the hub yet."),
    ).toBeVisible();
  });

  it("marks an unconnected source as unavailable instead of showing a number", async () => {
    render(<MetricCards metrics={mixed()} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Show 1 figure without a data source yet" }),
    );

    expect(screen.getByText("—")).toBeVisible();
    // An unmeasured figure never offers a destination to drill into.
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("hides a group whose every figure is unmeasured", async () => {
    render(<MetricCards metrics={payload({ groups: [unmeasuredGroup()] })} />);

    expect(screen.queryByRole("heading", { name: "Team operations" })).toBeNull();
    expect(
      screen.getByText("None of your figures have a data source yet."),
    ).toBeVisible();

    await userEvent.click(
      screen.getByRole("button", { name: "Show 1 figure without a data source yet" }),
    );
    expect(
      screen.getByRole("heading", { level: 2, name: "Team operations" }),
    ).toBeVisible();
  });

  it("offers no fold when every figure is measured", () => {
    render(<MetricCards metrics={payload()} />);
    expect(screen.queryByRole("button")).toBeNull();
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
