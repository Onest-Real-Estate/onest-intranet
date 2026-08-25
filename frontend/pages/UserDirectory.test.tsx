import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import UserDirectory from "@/pages/UserDirectory";
import type {
  DirectoryFilterOptions,
  DirectoryRow,
  DirectorySummary,
  UserDirectoryPageProps,
} from "@/types";

const pageProps = vi.hoisted(() => ({ current: {} as UserDirectoryPageProps }));
const routerGet = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/users" }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet },
}));

const ROW: DirectoryRow = {
  id: 9,
  name: "Bob Lee",
  email: "bob@onest.realestate",
  officeName: "Fairfax VA",
  officePathLabel: "Mid-Atlantic / Virginia / Fairfax VA",
  regionName: "Mid-Atlantic",
  isActive: true,
  accountState: { value: "active", label: "Active", tone: "success" },
  lastLoginAt: "2026-08-19T08:15:00+00:00",
  onboarding: { value: "complete", label: "Complete", tone: "success" },
  agentStatus: { value: "active", label: "Active", tone: "success" },
  agentIdentifier: "ON-4412",
  startDate: "2024-02-01",
  contract: {
    value: null as unknown as string,
    label: "Not connected",
    tone: "neutral",
    available: false,
  },
};

const FILTER_OPTIONS: DirectoryFilterOptions = {
  offices: [{ value: "7", label: "Mid-Atlantic / Fairfax VA" }],
  regions: [{ value: "3", label: "Mid-Atlantic" }],
  roles: [{ value: "branch_manager", label: "Branch Manager" }],
  accountStates: [
    { value: "active", label: "Active" },
    { value: "disabled", label: "Disabled" },
  ],
  onboardingStates: [
    { value: "complete", label: "Complete" },
    { value: "not_started", label: "Not started" },
  ],
  lastLoginWindows: [{ value: "over_90d", label: "Over 90 days ago" }],
  contract: {
    available: false,
    reason: "Agent contracts are not connected to the hub yet.",
    options: [],
  },
  agentStatuses: [
    { value: "active", label: "Active", tone: "success" },
    { value: "departed", label: "Departed", tone: "neutral" },
  ],
};

function setPage({
  items = [ROW],
  summary,
  visible = { administration: true, contract: true, onboarding: true },
  canOpenRecord = true,
  filterOptions = FILTER_OPTIONS,
}: {
  items?: DirectoryRow[];
  summary?: DirectorySummary;
  visible?: UserDirectoryPageProps["visible"];
  canOpenRecord?: boolean;
  filterOptions?: DirectoryFilterOptions;
} = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: ["web.view_users", "user.view_user_administration"],
      roles: ["System Admin"],
      roleLabel: "System Admin",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "00000000-0000-4000-8000-000000000001",
    features: {},
    primaryOffice: null,
    shell: {
      authorizationVersion: "v1",
      capabilitySchemaVersion: "p0-permissions-v1",
      help: { url: null },
      session: { authenticated: true },
    },
    notifications: null,
    users: {
      items,
      pagination: {
        page: 1,
        pageSize: 25,
        totalItems: items.length,
        totalPages: 1,
        hasNext: false,
        hasPrevious: false,
      },
      filters: {
        q: "",
        office: "",
        region: "",
        role: "",
        status: "",
        account: "",
        onboarding: "",
        contract: "",
        lastLogin: "",
      },
      sort: { key: "name", direction: "asc" },
    },
    summary: summary ?? {
      total: items.length,
      active: items.length,
      disabled: 0,
      pendingOnboarding: 0,
    },
    filterOptions,
    scope: { level: "brokerage", label: "Brokerage-wide" },
    visible,
    canOpenRecord,
  };
}

function rowFor(name: string): HTMLElement {
  const row = screen
    .getAllByRole("row")
    .find((candidate) => candidate.textContent?.includes(name));
  expect(row).toBeDefined();
  return row as HTMLElement;
}

beforeEach(() => {
  routerGet.mockClear();
  setPage();
  window.history.replaceState({}, "", "/operations/users");
});

describe("UserDirectory", () => {
  it("shows the scoped counts and the record destination for each row", () => {
    setPage({
      summary: { total: 42, active: 40, disabled: 2, pendingOnboarding: 3 },
    });
    render(<UserDirectory />);
    expect(screen.getByText("42")).toBeVisible();
    const row = rowFor("Bob Lee");
    expect(within(row).getByText("bob@onest.realestate")).toBeVisible();
    expect(within(row).getByRole("link", { name: /open the record/i })).toHaveAttribute(
      "href",
      "/operations/users/9/administration",
    );
  });

  it("delegates every filter change to the scoped server list", async () => {
    const user = userEvent.setup();
    render(<UserDirectory />);
    await user.click(screen.getByRole("combobox", { name: "Account" }));
    await user.click(screen.getByRole("option", { name: "Disabled" }));
    expect(routerGet).toHaveBeenCalledWith(
      expect.stringContaining("account=disabled"),
      {},
      expect.anything(),
    );
  });

  it("resets to the first page when the search term changes", async () => {
    const user = userEvent.setup();
    render(<UserDirectory />);
    await user.type(screen.getByRole("searchbox", { name: /search people/i }), "lee");
    await user.keyboard("{Enter}");
    const url = routerGet.mock.calls.at(-1)?.[0] as string;
    expect(url).toContain("q=lee");
    expect(url).toContain("page=1");
  });

  it("omits administrative columns a reader may not have", () => {
    const { agentStatus, agentIdentifier, startDate, contract, ...bare } = ROW;
    setPage({
      items: [bare],
      visible: { administration: false, contract: false, onboarding: true },
      canOpenRecord: false,
      filterOptions: { ...FILTER_OPTIONS, agentStatuses: undefined },
    });
    render(<UserDirectory />);
    // The column is absent, not blank: a dash would still confirm the field.
    expect(
      screen.queryByRole("columnheader", { name: /agent status/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Agent status" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open the record/i })).toBeNull();
    expect(screen.getByText(/not open their administrative record/i)).toBeVisible();
  });

  it("explains a disabled contract filter instead of hiding it", () => {
    render(<UserDirectory />);
    expect(screen.getByRole("combobox", { name: "Contract" })).toBeDisabled();
    expect(
      screen.getByText("Agent contracts are not connected to the hub yet."),
    ).toBeVisible();
  });

  it("distinguishes an empty scope from an empty search", () => {
    setPage({ items: [] });
    render(<UserDirectory />);
    expect(screen.getByText("Nobody in your scope yet")).toBeVisible();

    setPage({ items: [] });
    pageProps.current.users.filters.q = "zzz";
    render(<UserDirectory />);
    expect(screen.getByText("Nobody matches")).toBeVisible();
  });

  it("offers a shortcut to the disabled accounts still in scope", async () => {
    const user = userEvent.setup();
    setPage({
      summary: { total: 42, active: 40, disabled: 2, pendingOnboarding: 0 },
    });
    render(<UserDirectory />);
    await user.click(screen.getByRole("button", { name: /show them/i }));
    expect(routerGet).toHaveBeenCalledWith(
      expect.stringContaining("account=disabled"),
      {},
      expect.anything(),
    );
  });

  it("marks a disabled account in its own row", () => {
    setPage({
      items: [
        {
          ...ROW,
          isActive: false,
          accountState: {
            value: "disabled",
            label: "Disabled",
            tone: "destructive",
          },
        },
      ],
      summary: { total: 1, active: 0, disabled: 1, pendingOnboarding: 0 },
    });
    render(<UserDirectory />);
    expect(within(rowFor("Bob Lee")).getByText("Disabled")).toBeVisible();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<UserDirectory />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
