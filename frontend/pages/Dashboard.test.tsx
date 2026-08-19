import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Dashboard from "@/pages/Dashboard";
import type {
  DashboardPageProps,
  DashboardWidget,
  DashboardWidgetProp,
  User,
} from "@/types";

const pageProps = vi.hoisted(() => ({ current: {} as DashboardPageProps }));
const deferredReady = vi.hoisted(() => ({ current: true }));

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current }),
  Deferred: ({ children, fallback }: { children: ReactNode; fallback: ReactNode }) =>
    deferredReady.current ? children : fallback,
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { reload: vi.fn() },
}));

const user: User = {
  id: 1,
  email: "avery@onest.realestate",
  name: "Avery Johnson",
  permissions: [],
  roles: ["Users"],
  roleLabel: "Agent",
  isStaff: false,
  isSuperuser: false,
};

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

function setPage() {
  const widgets: Record<DashboardWidgetProp, DashboardWidget<never>> = {
    metrics: pending("Metrics are unavailable."),
    quickApps: pending("Tools are unavailable."),
    announcements: pending("News is not connected."),
    transactions: pending("Transactions are not connected."),
    training: pending("Training is not connected."),
    schedule: pending("Calendar is not connected."),
    actionItems: pending("Tasks are not connected."),
    market: pending("Market data is not connected."),
    documents: pending("Documents are not connected."),
  };
  pageProps.current = {
    user,
    csrfToken: "token",
    requestId: "request-1",
    features: {},
    primaryOffice: null,
    shell: {
      authorizationVersion: "access-v1",
      help: { url: null },
      session: { authenticated: true },
    },
    greeting: {
      salutation: "Good morning",
      name: "Avery",
      dateLabel: "Wednesday, August 19",
      dateIso: "2026-08-19",
      timezone: "America/New_York",
    },
    ...widgets,
  };
}

beforeEach(() => {
  deferredReady.current = true;
  setPage();
});

describe("Dashboard", () => {
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

  it("puts today's obligations first in mobile source order", () => {
    render(<Dashboard />);

    const titles = screen
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.textContent);
    expect(titles.indexOf("My day")).toBeLessThan(
      titles.indexOf("News & announcements"),
    );
    expect(titles.indexOf("Action items")).toBeLessThan(
      titles.indexOf("Active transactions"),
    );
  });

  it("shows skeletons while deferred widgets are loading", () => {
    deferredReady.current = false;
    render(<Dashboard />);

    expect(
      screen.getAllByRole("heading", { name: "Loading metrics" }).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("Calendar is not connected.")).toBeNull();
  });
});
