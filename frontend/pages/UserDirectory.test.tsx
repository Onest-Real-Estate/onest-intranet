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
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/users" }),
  Head: () => null,
  Link: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: ReactNode;
    className?: string;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
  router: { get: routerGet, post: routerPost },
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
  roles: ["Realtor", "Branch Manager", "Compliance"],
  account: { version: "2026-09-01T00:00:00+00:00" },
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
  permissions = ["web.view_users", "user.view_user_administration"],
  errors = { fields: {}, form: [] },
}: {
  permissions?: string[];
  errors?: UserDirectoryPageProps["errors"];
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
      permissions,
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
    pageSizeOptions: [10, 25, 50, 100],
    errors,
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
  routerPost.mockClear();
  setPage();
  window.history.replaceState({}, "", "/operations/users");
});

describe("UserDirectory", () => {
  it("sits under the People tabs this reader may open", () => {
    setPage({
      permissions: ["web.view_users", "web.view_new_agents", "web.add_users"],
    });
    render(<UserDirectory />);
    const tabs = screen.getByRole("navigation", { name: "People sections" });
    expect(within(tabs).getByRole("link", { name: "Users" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(tabs).getByRole("link", { name: "New agents" })).toBeVisible();
    // No grant, no tab: roles are not assignable by this reader.
    expect(within(tabs).queryByRole("link", { name: /Roles/ })).toBeNull();
    expect(screen.getByRole("link", { name: /Add user/ })).toHaveAttribute(
      "href",
      "/operations/users/new",
    );
  });

  it("offers Add user only with the grant", () => {
    render(<UserDirectory />);
    expect(screen.queryByRole("link", { name: /Add user/ })).toBeNull();
  });

  it("shows each person with their status and a way to edit the record", () => {
    render(<UserDirectory />);
    const row = rowFor("Bob Lee");
    expect(within(row).getByText("bob@onest.realestate")).toBeVisible();
    expect(within(row).getAllByText("Active").length).toBeGreaterThan(0);
    expect(within(row).getByRole("link", { name: /Edit/ })).toHaveAttribute(
      "href",
      "/operations/users/9/administration",
    );
  });

  it("shows roles as chips, folding the rest into a count", () => {
    render(<UserDirectory />);
    const row = rowFor("Bob Lee");
    expect(within(row).getByText("Realtor")).toBeVisible();
    expect(within(row).getByText("Branch Manager")).toBeVisible();
    expect(within(row).getByText("+1")).toHaveAttribute("title", "Compliance");
  });

  it("links role chips to the role workspace only for a reader who may assign", () => {
    setPage({ permissions: ["web.view_users", "web.assign_user_roles"] });
    render(<UserDirectory />);
    expect(
      within(rowFor("Bob Lee")).getByRole("link", { name: /Manage roles for Bob Lee/ }),
    ).toHaveAttribute("href", "/operations/role-assignments/9");
  });

  it("deactivates from the row with a reason and comes back to the list", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/operations/users?role=realtor");
    render(<UserDirectory />);

    await user.click(
      within(rowFor("Bob Lee")).getByRole("button", { name: /Deactivate/ }),
    );
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Deactivate account" });
    // No reason, no lockout.
    expect(confirm).toBeDisabled();

    await user.type(
      within(dialog).getByLabelText(/Business reason/),
      "Left the brokerage.",
    );
    await user.click(confirm);

    expect(routerPost).toHaveBeenCalledOnce();
    const [url, data] = routerPost.mock.calls[0];
    expect(url).toBe("/operations/users/9/account-state");
    expect(data).toEqual({
      action: "disable",
      business_reason: "Left the brokerage.",
      expected_version: "2026-09-01T00:00:00+00:00",
      returnTo: "users",
      returnQuery: "?role=realtor",
    });
  });

  it("offers Activate on a deactivated account", () => {
    setPage({
      items: [
        {
          ...ROW,
          isActive: false,
          accountState: { value: "disabled", label: "Disabled", tone: "destructive" },
        },
      ],
    });
    render(<UserDirectory />);
    const row = rowFor("Bob Lee");
    expect(within(row).getByText("Disabled")).toBeVisible();
    expect(within(row).getByRole("button", { name: /Activate/ })).toBeVisible();
  });

  it("shows no account action where the server did not offer one", () => {
    const { account, ...withoutAccount } = ROW;
    setPage({ items: [withoutAccount] });
    render(<UserDirectory />);
    expect(
      within(rowFor("Bob Lee")).queryByRole("button", { name: /Deactivate/ }),
    ).toBeNull();
  });

  it("delegates every filter change to the scoped server list", async () => {
    const user = userEvent.setup();
    render(<UserDirectory />);
    await user.click(screen.getByRole("combobox", { name: "Role" }));
    await user.click(screen.getByRole("option", { name: "Branch Manager" }));
    expect(routerGet).toHaveBeenCalledWith(
      expect.stringContaining("role=branch_manager"),
      {},
      expect.anything(),
    );
  });

  it("narrows to deactivated accounts from the quick view", async () => {
    const user = userEvent.setup();
    setPage({ summary: { total: 42, active: 40, disabled: 2, pendingOnboarding: 0 } });
    render(<UserDirectory />);
    await user.click(screen.getByRole("button", { name: /^Deactivated/ }));
    expect(routerGet).toHaveBeenCalledWith(
      expect.stringContaining("account=disabled"),
      {},
      expect.anything(),
    );
  });

  it("sorts from the toolbar through the URL", async () => {
    const user = userEvent.setup();
    render(<UserDirectory />);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Sort by" }),
      "lastLogin-desc",
    );
    const url = routerGet.mock.calls.at(-1)?.[0] as string;
    expect(url).toContain("sort=lastLogin");
    expect(url).toContain("direction=desc");
  });

  it("changes the page size through the URL", async () => {
    const user = userEvent.setup();
    render(<UserDirectory />);
    await user.selectOptions(
      screen.getByRole("combobox", { name: /Rows per page/ }),
      "50",
    );
    expect(routerGet.mock.calls.at(-1)?.[0]).toContain("pageSize=50");
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
    const { agentStatus, agentIdentifier, startDate, contract, account, ...bare } = ROW;
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
    expect(screen.queryByRole("link", { name: /Edit/ })).toBeNull();
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

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<UserDirectory />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
