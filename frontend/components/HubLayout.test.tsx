import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { HubLayout } from "@/components/HubLayout";
import {
  HUB_ADMIN_NAV,
  HUB_FEATURE_KEYS,
  HUB_NAV_EXPANSION_STORAGE_KEY,
  resolveHubNav,
} from "@/lib/hub-nav";
import type { HubFeatures, PageProps, PrimaryOffice, User } from "@/types";

const pageProps = vi.hoisted(() => ({ current: {} as PageProps, url: "/dashboard" }));
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: pageProps.url }),
  Link: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
  Head: () => null,
  router: { post: routerPost },
}));

const agent: User = {
  id: 1,
  email: "agent@onest.realestate",
  name: "Avery Johnson",
  permissions: [],
  roles: ["Users"],
  roleLabel: "Agent",
  isStaff: false,
  isSuperuser: false,
};

const office: PrimaryOffice = {
  id: 7,
  name: "Cedar Ridge branch",
  regionName: "Midwest",
};

function features(overrides: HubFeatures = {}): HubFeatures {
  const base = Object.fromEntries(HUB_FEATURE_KEYS.map((key) => [key, true]));
  return { ...base, ...overrides };
}

function setPage(overrides: Partial<PageProps> = {}, url = "/dashboard") {
  pageProps.current = {
    user: agent,
    csrfToken: "token",
    requestId: "req-1",
    features: features(),
    primaryOffice: office,
    ...overrides,
  };
  pageProps.url = url;
}

/** jsdom has no matchMedia; the sidebar reads it to pick drawer vs rail. */
function setViewport(width: number) {
  window.innerWidth = width;
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: width < 768,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

function nav() {
  return screen.getByRole("navigation", { name: "Hub sections" });
}

/**
 * Visible item labels. Every mode renders from the same resolved registry.
 */
function navTitles() {
  return within(nav())
    .getAllByRole("link")
    .map((link) => link.querySelector("span")?.textContent ?? "");
}

function approvedTitles() {
  return resolveHubNav(agent, features(), office).flatMap((group) =>
    group.items.map((item) => item.label),
  );
}

function adminPermissions() {
  return HUB_ADMIN_NAV.flatMap((item) => item.permissions.all ?? []);
}

beforeEach(() => {
  routerPost.mockClear();
  window.localStorage.clear();
  setViewport(1280);
  setPage();
});

function renderLayout() {
  return render(
    <HubLayout>
      <p>content</p>
    </HubLayout>,
  );
}

/** The footer, scoped so the header's copy of the name does not match too. */
function footer(): HTMLElement {
  const el = document.querySelector<HTMLElement>('[data-slot="sidebar-footer"]');
  if (!el) {
    throw new Error("expected the sidebar to render a footer");
  }
  return el;
}

describe("HubLayout navigation", () => {
  it("renders the approved groups and destinations in order", () => {
    render(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    expect(navTitles()).toEqual(approvedTitles());
  });

  it("points every destination at a real path, never an empty href", () => {
    render(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    for (const link of within(nav()).getAllByRole("link")) {
      expect(link.getAttribute("href")).toMatch(/^\/[\w/-]+$/);
    }
  });

  it("marks the current page and only the current page", () => {
    setPage({}, "/dashboard?tab=today");
    render(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    const current = within(nav())
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent("Dashboard");
  });

  it("renders an explicitly registered disabled module as Soon", () => {
    setPage({ features: features({ "my-contract": false }) });
    render(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    const contract = within(nav()).getByRole("link", { name: /My contract/ });
    expect(contract).toHaveTextContent("Soon");
    expect(contract).toHaveAccessibleDescription("My contract is coming soon");
  });

  it("updates a module immediately when availability changes", () => {
    const rendered = renderLayout();
    expect(
      within(nav()).getByRole("link", { name: "My contract" }),
    ).toBeInTheDocument();

    setPage({ features: features({ "my-contract": false }) });
    rendered.rerender(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );

    const contract = within(nav()).getByRole("link", { name: /My contract/ });
    expect(contract).toHaveTextContent("Soon");
    expect(contract).toHaveAccessibleDescription("My contract is coming soon");
  });

  it("renders no destinations while permission context is incomplete", () => {
    setPage({
      user: { ...agent, permissions: undefined } as unknown as User,
    });
    renderLayout();
    expect(within(nav()).queryAllByRole("link")).toHaveLength(0);
  });

  it("hides office destinations when there is no safe office context", () => {
    setPage({
      primaryOffice: null,
    });
    render(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    expect(screen.queryByText("My office")).not.toBeInTheDocument();
    expect(
      within(nav()).queryByRole("link", { name: /Office info/ }),
    ).not.toBeInTheDocument();
  });

  it("shows a manager who is also a Realtor one sidebar with no duplicates", () => {
    setPage({
      user: {
        ...agent,
        roles: ["Branch Managers", "Users"],
        roleLabel: "Branch manager",
        permissions: ["user.view_user"],
      },
    });
    render(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    expect(screen.getAllByRole("navigation", { name: "Hub sections" })).toHaveLength(1);
    const labels = within(nav())
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("integrates authorized administrative destinations into the same sidebar", () => {
    setPage({
      user: {
        ...agent,
        roles: ["Admins", "Users"],
        roleLabel: "Admin",
        permissions: adminPermissions(),
      },
    });
    renderLayout();
    expect(screen.getByText("Administration")).toBeInTheDocument();
    expect(
      within(nav())
        .getAllByRole("region")
        .map((group) => group.getAttribute("aria-label")),
    ).toEqual(["People", "Operations", "Content", "Governance & support"]);
    for (const item of HUB_ADMIN_NAV) {
      expect(
        within(nav())
          .getAllByRole("link")
          .find((link) => link.getAttribute("href") === item.route.href),
      ).toBeInTheDocument();
    }
  });

  it("marks a nested users detail route active without activating Add New User", () => {
    setPage(
      {
        user: {
          ...agent,
          permissions: ["web.view_users", "web.add_users"],
        },
      },
      "/operations/users/42?tab=roles",
    );
    renderLayout();
    expect(within(nav()).getByRole("link", { name: /^Users/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      within(nav()).getByRole("link", { name: /Add New User/ }),
    ).not.toHaveAttribute("aria-current");
  });

  it("supports keyboard-operated nested sections and persists only section keys", async () => {
    setPage({
      user: {
        ...agent,
        permissions: ["web.view_users", "web.view_new_agents"],
      },
    });
    renderLayout();
    const people = within(nav()).getByRole("button", { name: "People" });
    expect(people).toHaveAttribute("aria-expanded", "true");

    people.focus();
    await userEvent.keyboard("{Enter}");

    expect(people).toHaveAttribute("aria-expanded", "false");
    expect(window.localStorage.getItem(HUB_NAV_EXPANSION_STORAGE_KEY)).not.toContain(
      "admin-people",
    );
  });

  it("forces the active deep-link section open without trusting stale storage", () => {
    window.localStorage.setItem(HUB_NAV_EXPANSION_STORAGE_KEY, '["unknown-section"]');
    setPage(
      {
        user: { ...agent, permissions: ["web.view_users"] },
      },
      "/operations/users/42",
    );
    renderLayout();
    expect(within(nav()).getByRole("button", { name: "People" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(within(nav()).getByRole("link", { name: "Users" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("removes the Administration heading after the last permission is revoked", () => {
    setPage({ user: { ...agent, permissions: ["web.view_compliance"] } });
    const rendered = renderLayout();
    expect(screen.getByText("Administration")).toBeInTheDocument();
    expect(screen.getByText("Governance & support")).toBeInTheDocument();
    expect(screen.queryByText("People")).not.toBeInTheDocument();
    expect(screen.queryByText("Operations")).not.toBeInTheDocument();
    expect(screen.queryByText("Content")).not.toBeInTheDocument();

    setPage({ user: agent });
    rendered.rerender(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    expect(screen.queryByText("Administration")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Compliance/ })).not.toBeInTheDocument();
  });

  it("keeps the same order and destinations in the mobile drawer", async () => {
    setViewport(390);
    render(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    await userEvent.click(screen.getAllByRole("button", { name: /sidebar/i })[0]);
    expect(navTitles()).toEqual(approvedTitles());
  });

  it("supports the documented keyboard shortcut for the collapsed rail", async () => {
    renderLayout();
    const sidebar = document.querySelector('[data-slot="sidebar"]');
    expect(sidebar).toHaveAttribute("data-state", "expanded");
    await userEvent.keyboard("{Control>}b{/Control}");
    expect(sidebar).toHaveAttribute("data-state", "collapsed");
    expect(within(nav()).getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("keeps long specialty labels usable in the mobile drawer", async () => {
    setViewport(390);
    setPage({
      user: {
        ...agent,
        permissions: ["web.assign_user_roles", "web.view_platform_tasks"],
      },
    });
    renderLayout();
    await userEvent.click(screen.getAllByRole("button", { name: /sidebar/i })[0]);
    expect(
      within(nav()).getByRole("link", { name: /Assign User Roles/ }),
    ).toBeVisible();
    expect(within(nav()).getByRole("link", { name: /Platform Tasks/ })).toBeVisible();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("HubLayout account card", () => {
  it("names the signed-in user and their email in the sidebar footer", () => {
    renderLayout();
    expect(within(footer()).getByText("Avery Johnson")).toBeInTheDocument();
    expect(within(footer()).getByText("agent@onest.realestate")).toBeInTheDocument();
  });

  it("takes the identity block to the profile page", () => {
    renderLayout();
    expect(
      within(footer()).getByRole("link", { name: /Avery Johnson/ }),
    ).toHaveAttribute("href", "/profile");
  });

  it("ends the session through the logout route", async () => {
    renderLayout();
    await userEvent.click(screen.getByRole("button", { name: "Sign out Avery" }));
    expect(routerPost).toHaveBeenCalledWith("/logout");
  });

  it("renders no account card for a signed-out visitor", () => {
    setPage({ user: null });
    renderLayout();
    expect(screen.queryByRole("button", { name: /Sign out/ })).not.toBeInTheDocument();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = renderLayout();
    expect(await axe(container)).toHaveNoViolations();
  });
});
