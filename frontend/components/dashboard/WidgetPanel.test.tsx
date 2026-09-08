import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { WidgetPanel } from "@/components/dashboard/WidgetPanel";
import type { DashboardWidget } from "@/types";

const routerReload = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { reload: routerReload },
}));

const generatedAt = "2026-08-19T14:00:00-04:00";

function ready(): DashboardWidget<{ message: string }> {
  return {
    status: "ready",
    version: 1,
    generatedAt,
    data: { message: "Scoped production data" },
    emptyState: null,
    unavailable: null,
    meta: {},
  };
}

function empty(): DashboardWidget<never> {
  return {
    status: "empty",
    version: 1,
    generatedAt,
    data: null,
    emptyState: {
      title: "Nothing due today",
      description: "Schedule your first appointment to see it here.",
      actionLabel: "Open calendar",
      actionHref: "/hub/my-reservations",
    },
    unavailable: null,
    meta: {},
  };
}

function unavailable(retryable: boolean): DashboardWidget<never> {
  return {
    status: "unavailable",
    version: 1,
    generatedAt,
    data: null,
    emptyState: null,
    unavailable: {
      reason: retryable
        ? "This widget could not be loaded just now."
        : "Your calendar is not connected to the hub yet.",
      retryable,
      actionLabel: retryable ? undefined : "Go to reservations",
      actionHref: retryable ? undefined : "/hub/my-reservations",
    },
    meta: {},
  };
}

beforeEach(() => routerReload.mockReset());

describe("WidgetPanel", () => {
  it("passes ready data to the widget without adding another card", () => {
    render(
      <WidgetPanel title="My day" propName="schedule" widget={ready()}>
        {(data) => <p>{data.message}</p>}
      </WidgetPanel>,
    );

    expect(screen.getByText("Scoped production data")).toBeVisible();
    expect(screen.queryByText("Not connected yet")).toBeNull();
  });

  it("renders an instructive empty state and its next action", () => {
    render(
      <WidgetPanel title="My day" propName="schedule" widget={empty()}>
        {() => null}
      </WidgetPanel>,
    );

    expect(screen.getByRole("heading", { name: "Nothing due today" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open calendar" })).toHaveAttribute(
      "href",
      "/hub/my-reservations",
    );
  });

  it("links unconnected modules to their useful destination without retrying", () => {
    render(
      <WidgetPanel title="My day" propName="schedule" widget={unavailable(false)}>
        {() => null}
      </WidgetPanel>,
    );

    expect(screen.getByText("Not connected yet")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(screen.getByRole("link", { name: "Go to reservations" })).toHaveAttribute(
      "href",
      "/hub/my-reservations",
    );
  });

  it("retries only the failed prop and exposes progress", async () => {
    let finish: (() => void) | undefined;
    routerReload.mockImplementation((options) => {
      if (!options) {
        return;
      }
      options.onStart?.({} as never);
      finish = () => options.onFinish?.({} as never);
    });
    render(
      <WidgetPanel title="Market snapshot" propName="market" widget={unavailable(true)}>
        {() => null}
      </WidgetPanel>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(routerReload).toHaveBeenCalledWith(
      expect.objectContaining({ only: ["market"] }),
    );
    expect(screen.getByRole("button", { name: "Retrying…" })).toBeDisabled();

    act(() => finish?.());
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  });

  it("has no detectable accessibility violations in failure state", async () => {
    const { container } = render(
      <WidgetPanel title="Market snapshot" propName="market" widget={unavailable(true)}>
        {() => null}
      </WidgetPanel>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
