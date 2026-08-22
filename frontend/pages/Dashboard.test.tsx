import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { DASHBOARD_PROFILE_STORAGE_KEY } from "@/lib/dashboard/resolve";
import Dashboard from "@/pages/Dashboard";
import type {
  DashboardPageProps,
  DashboardWidget,
  DashboardWidgetProp,
  User,
} from "@/types";

const pageProps = vi.hoisted(() => ({ current: {} as DashboardPageProps }));
const deferredReady = vi.hoisted(() => ({ current: true }));
const routerReload = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current }),
  Deferred: ({ children, fallback }: { children: ReactNode; fallback: ReactNode }) =>
    deferredReady.current ? children : fallback,
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { reload: routerReload },
}));

/** Every permission the widget registry knows about. */
const ALL_PERMISSIONS = [
  "web.view_own_tasks",
  "web.view_own_transactions",
  "web.view_transactions",
  "web.view_new_agents",
  "web.manage_new_agent_onboarding",
  "web.view_agent_contracts",
  "web.view_compliance",
  "web.view_office_tasks",
  "web.view_platform_tasks",
  "web.view_inventory",
  "web.view_reservations",
  "web.view_users",
  "web.view_it_support",
  "web.view_feedback",
  "user.view_user_administration",
];

function reader(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    email: "avery@onest.realestate",
    name: "Avery Johnson",
    headshotUrl: null,
    permissions: ["web.view_own_tasks", "web.view_own_transactions"],
    roles: ["realtor"],
    roleLabel: "Realtor",
    isStaff: false,
    isSuperuser: false,
    ...overrides,
  };
}

function pending(reason: string): DashboardWidget<never> {
  return {
    status: "unavailable",
    version: 1,
    generatedAt: "2026-08-19T09:00:00-04:00",
    data: null,
    emptyState: null,
    unavailable: { reason, retryable: false },
    meta: {},
  };
}

/** Only the props a server provider actually fills today. */
const BACKED_PROPS: DashboardWidgetProp[] = [
  "metrics",
  "quickApps",
  "announcements",
  "transactions",
  "training",
  "schedule",
  "actionItems",
  "market",
  "documents",
];

function setPage(overrides: Partial<DashboardPageProps> = {}) {
  const widgets: Partial<Record<DashboardWidgetProp, DashboardWidget<never>>> = {};
  for (const prop of BACKED_PROPS) {
    widgets[prop] = pending(`${prop} is not connected.`);
  }
  pageProps.current = {
    user: reader(),
    csrfToken: "token",
    requestId: "request-1",
    features: {},
    primaryOffice: null,
    shell: {
      authorizationVersion: "access-v1",
      capabilitySchemaVersion: "p0-permissions-v1",
      help: { url: null },
      session: { authenticated: true },
    },
    notifications: null,
    greeting: {
      salutation: "Good morning",
      name: "Avery",
      dateLabel: "Wednesday, August 19",
      dateIso: "2026-08-19",
      timezone: "America/New_York",
    },
    ...widgets,
    ...overrides,
  };
}

function panelTitles(): string[] {
  return screen
    .getAllByRole("heading", { level: 2 })
    .map((heading) => heading.textContent ?? "");
}

beforeEach(() => {
  deferredReady.current = true;
  routerReload.mockReset();
  window.localStorage.clear();
  setPage();
});

describe("Dashboard shell", () => {
  it("uses the server-local greeting and date", () => {
    render(<Dashboard />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Good morning, Avery" }),
    ).toBeVisible();
    expect(screen.getByText("Wednesday, August 19")).toHaveAttribute(
      "datetime",
      "2026-08-19",
    );
  });

  it("leads with the metrics row, then brokerage news", () => {
    render(<Dashboard />);
    const titles = panelTitles();
    expect(titles[0]).toBe("Performance");
    expect(titles[1]).toBe("News & announcements");
  });

  it("keeps role-defining work before supporting utilities in source order", () => {
    // The columns collapse into one on a phone. Keeping the primary workflow
    // first in the DOM also keeps keyboard and desktop visual order aligned.
    render(<Dashboard />);
    const titles = panelTitles();

    expect(titles.indexOf("Active transactions")).toBeLessThan(
      titles.indexOf("Action items"),
    );
    expect(titles.indexOf("Training & resources")).toBeLessThan(
      titles.indexOf("My day"),
    );
  });

  it("shows skeletons while deferred widgets are loading", () => {
    deferredReady.current = false;
    render(<Dashboard />);

    // The metrics row's skeleton is four loading stat cards.
    expect(screen.getAllByText("Loading").length).toBeGreaterThanOrEqual(4);
    expect(screen.queryByText("schedule is not connected.")).toBeNull();
  });

  it("renders nothing for a page with no user", () => {
    setPage({ user: null });
    const { container } = render(<Dashboard />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("per-role dashboards", () => {
  it.each([
    ["system_admin", "Operational activity", "Team tasks"],
    ["principal_broker", "Closing pipeline", "Awaiting signature"],
    ["regional_manager", "Closing pipeline", "Team tasks"],
    ["transaction_coordinator", "Closing pipeline", "Awaiting signature"],
    ["branch_manager", "Closing pipeline", "My day"],
    ["branch_admin", "Agent onboarding", "My day"],
    ["realtor", "Active transactions", "My day"],
    ["marketing_team", "Feedback signals", "My day"],
    ["accountant", "Closing pipeline", "Awaiting signature"],
    ["compliance", "Compliance exceptions", "Awaiting signature"],
    ["it_support", "Support queue", "Team tasks"],
  ])(
    "puts %s's defining workflow before its supporting rail",
    (role, workflow, support) => {
      setPage({
        user: reader({ roles: [role], permissions: ALL_PERMISSIONS }),
      });
      render(<Dashboard />);
      const titles = panelTitles();

      expect(titles).toContain(workflow);
      expect(titles).toContain(support);
      expect(titles.indexOf(workflow)).toBeLessThan(titles.indexOf(support));
    },
  );

  it("gives an agent their own book of business and no team panels", () => {
    render(<Dashboard />);
    const titles = panelTitles();

    expect(titles).toContain("Active transactions");
    expect(titles).toContain("Market snapshot");
    expect(titles).not.toContain("Closing pipeline");
    expect(titles).not.toContain("Agent onboarding");
  });

  it("gives a branch manager the office's pipeline and people", () => {
    setPage({
      user: reader({ roles: ["branch_manager"], permissions: ALL_PERMISSIONS }),
    });
    render(<Dashboard />);
    const titles = panelTitles();

    expect(titles).toContain("Closing pipeline");
    expect(titles).toContain("Agent onboarding");
    expect(titles).toContain("Room utilization");
    expect(titles).not.toContain("Market snapshot");
  });

  it("gives compliance its exception queue", () => {
    setPage({
      user: reader({ roles: ["compliance"], permissions: ALL_PERMISSIONS }),
    });
    render(<Dashboard />);

    expect(panelTitles()).toContain("Compliance exceptions");
  });

  it("gives IT support the support queue", () => {
    setPage({
      user: reader({ roles: ["it_support"], permissions: ALL_PERMISSIONS }),
    });
    render(<Dashboard />);

    const titles = panelTitles();
    expect(titles).toContain("Support queue");
    expect(titles.indexOf("Support queue")).toBeLessThan(titles.indexOf("Team tasks"));
  });

  it("never renders the same panel twice", () => {
    setPage({
      user: reader({ roles: ["system_admin"], permissions: ALL_PERMISSIONS }),
    });
    render(<Dashboard />);
    const titles = panelTitles();

    expect(new Set(titles).size).toBe(titles.length);
  });

  it("lets a rail-only scoped dashboard use the full working width", () => {
    setPage({
      user: reader({ roles: ["system_admin"], permissions: ALL_PERMISSIONS }),
      scope: {
        selectedKey: "self",
        options: [{ key: "self", label: "My work", level: "self" }],
      },
    });
    const { container } = render(<Dashboard />);

    expect(container.querySelector('[data-dashboard-column="main"]')).toBeNull();
    expect(container.querySelector('[data-dashboard-column="rail"]')).toHaveClass(
      "xl:col-span-12",
    );
  });
});

describe("widget states", () => {
  it("labels illustrative figures as preview data", () => {
    setPage({
      user: reader({ roles: ["branch_manager"], permissions: ALL_PERMISSIONS }),
    });
    render(<Dashboard />);

    expect(screen.getAllByText("Preview data").length).toBeGreaterThan(0);
  });

  it("keeps an unconnected module distinct from a zero", () => {
    render(<Dashboard />);

    expect(screen.getAllByText("Not connected yet").length).toBeGreaterThan(0);
  });

  it("withholds a restricted panel instead of implying nothing to review", () => {
    // Compliance role, but the compliance permission has been revoked.
    setPage({ user: reader({ roles: ["compliance"], permissions: [] }) });
    render(<Dashboard />);

    expect(
      screen.getAllByRole("heading", { name: "Restricted" }).length,
    ).toBeGreaterThan(0);
    expect(panelTitles()).toContain("Compliance exceptions");
  });

  it("marks the page stale when effective access changes mid-session", async () => {
    const { rerender } = render(<Dashboard />);
    expect(screen.queryByText(/roles or scope changed/)).toBeNull();

    setPage({
      shell: {
        ...pageProps.current.shell,
        authorizationVersion: "access-v2",
      },
    });
    rerender(<Dashboard />);

    expect(screen.getByText(/roles or scope changed/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(routerReload).toHaveBeenCalled();
  });
});

describe("profile switching", () => {
  it("offers no switcher to a single-role reader", () => {
    render(<Dashboard />);
    expect(screen.queryByLabelText("Dashboard view")).toBeNull();
  });

  it("lets a multi-role reader change presentation without changing access", async () => {
    setPage({
      user: reader({
        roles: ["branch_manager", "realtor"],
        permissions: ALL_PERMISSIONS,
      }),
    });
    render(<Dashboard />);

    const switcher = screen.getByLabelText("Dashboard view");
    expect(within(switcher).getByText("Branch Manager")).toBeVisible();

    await userEvent.click(switcher);
    await userEvent.click(screen.getByRole("option", { name: "Agent" }));

    expect(panelTitles()).toContain("Market snapshot");
    expect(panelTitles()).not.toContain("Closing pipeline");
    // Presentation only: nothing was asked of the server.
    expect(routerReload).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(DASHBOARD_PROFILE_STORAGE_KEY)).toBe("agent");
  });

  it("cannot show a widget the reader has no permission for", async () => {
    setPage({
      user: reader({
        roles: ["branch_manager", "realtor"],
        permissions: ["web.view_own_tasks", "web.view_own_transactions"],
      }),
    });
    render(<Dashboard />);

    await userEvent.click(screen.getByLabelText("Dashboard view"));
    await userEvent.click(screen.getByRole("option", { name: "Branch Manager" }));

    const titles = panelTitles();
    expect(titles).not.toContain("Agent onboarding");
    expect(titles).not.toContain("Room utilization");
  });

  it("ignores a remembered profile the reader no longer holds", () => {
    window.localStorage.setItem(DASHBOARD_PROFILE_STORAGE_KEY, "systemAdmin");
    render(<Dashboard />);

    expect(panelTitles()).not.toContain("Operational activity");
    expect(panelTitles()).toContain("Active transactions");
  });
});

describe("accessibility", () => {
  it("has no detectable violations for an administrative dashboard", async () => {
    setPage({
      user: reader({ roles: ["branch_manager"], permissions: ALL_PERMISSIONS }),
    });
    const { container } = render(<Dashboard />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
