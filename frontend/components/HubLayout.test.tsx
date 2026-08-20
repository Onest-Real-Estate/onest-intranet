import { act, render, screen, waitFor, within } from "@testing-library/react";
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
const routerReload = vi.hoisted(() => vi.fn());
const routerEvents = vi.hoisted(
  () => new Map<string, Set<(event: CustomEvent) => unknown>>(),
);
const routerOn = vi.hoisted(() =>
  vi.fn((name: string, callback: (event: CustomEvent) => unknown) => {
    const listeners = routerEvents.get(name) ?? new Set();
    listeners.add(callback);
    routerEvents.set(name, listeners);
    return () => listeners.delete(callback);
  }),
);

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: pageProps.url }),
  Link: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
  Head: () => null,
  router: { on: routerOn, post: routerPost, reload: routerReload },
}));

const agent: User = {
  id: 1,
  email: "agent@onest.realestate",
  name: "Avery Johnson",
  headshotUrl: null,
  permissions: [],
  roles: ["realtor"],
  roleLabel: "Realtor",
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
    shell: {
      authorizationVersion: "access-v1",
      capabilitySchemaVersion: "p0-permissions-v1",
      help: { url: null },
      session: { authenticated: true },
    },
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
  routerReload.mockClear();
  routerOn.mockClear();
  routerEvents.clear();
  window.localStorage.clear();
  window.requestAnimationFrame = (callback) => {
    return window.setTimeout(() => callback(0), 0);
  };
  setViewport(1280);
  setPage();
});

function fireRouterEvent(name: string, detail: Record<string, unknown> = {}) {
  act(() => {
    for (const listener of routerEvents.get(name) ?? []) {
      listener(new CustomEvent(name, { detail }));
    }
  });
}

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

  it("derives page context from the active route when none is supplied", () => {
    renderLayout();
    expect(screen.getByText("Dashboard", { selector: "header p" })).toBeVisible();
  });

  it("renders typed breadcrumbs and falls back from an unsafe back target", () => {
    render(
      <HubLayout
        context={{
          title: "A very long record name",
          breadcrumbs: [
            { label: "Dashboard", href: "/dashboard" },
            { label: "Record" },
          ],
          back: { label: "Go back", href: "https://outside.example" },
        }}
      >
        <p>content</p>
      </HubLayout>,
    );
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Go back" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
  });

  it.each([
    ["standard", "page-shell"],
    ["wide", "max-w-[1600px]"],
    ["focused", "max-w-2xl"],
  ] as const)("supports the %s content layout", (variant, expectedClass) => {
    render(
      <HubLayout variant={variant}>
        <p>content</p>
      </HubLayout>,
    );
    expect(document.getElementById("hub-content")).toHaveClass(expectedClass);
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
        roles: ["branch_manager", "realtor"],
        roleLabel: "Branch Manager",
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
        roles: ["system_admin", "realtor"],
        roleLabel: "System Admin",
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

  it("traps focus in the mobile drawer and restores it when Escape closes", async () => {
    setViewport(390);
    renderLayout();
    const trigger = screen.getAllByRole("button", { name: /sidebar/i })[0];
    await userEvent.click(trigger);
    const drawer = screen.getByRole("dialog");
    expect(drawer).toContainElement(document.activeElement as HTMLElement);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("closes the mobile drawer and focuses content after navigation", async () => {
    setViewport(390);
    renderLayout();
    await userEvent.click(screen.getAllByRole("button", { name: /sidebar/i })[0]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireRouterEvent("navigate");

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(document.getElementById("hub-content")).toHaveFocus();
    });
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

describe("HubLayout lifecycle and entry points", () => {
  it("announces route loading without hiding the current content", () => {
    renderLayout();
    fireRouterEvent("start");
    expect(document.getElementById("hub-content")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Loading page");

    fireRouterEvent("finish");
    expect(document.getElementById("hub-content")).toHaveAttribute(
      "aria-busy",
      "false",
    );
  });

  it("offers a recoverable network error and retries fresh", async () => {
    renderLayout();
    fireRouterEvent("networkError", { error: new Error("offline") });
    expect(screen.getByRole("alert")).toHaveTextContent("You’re offline");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(routerReload).toHaveBeenCalledWith({ fresh: true });
  });

  it("offers sign-in again when an authenticated request expires", () => {
    renderLayout();
    fireRouterEvent("httpException", { response: { status: 401 } });
    expect(screen.getByRole("alert")).toHaveTextContent("Your session has expired");
    expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("opens only a backend-approved help destination in a new tab", () => {
    setPage({
      shell: {
        authorizationVersion: "access-v1",
        capabilitySchemaVersion: "p0-permissions-v1",
        help: { url: "https://help.onest.realestate/hub" },
        session: { authenticated: true },
      },
    });
    renderLayout();
    expect(
      screen.getByRole("link", { name: "Open help centre in a new tab" }),
    ).toHaveAttribute("rel", "noopener noreferrer");
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

  it("summarizes identity and office in the header user menu", async () => {
    renderLayout();
    await userEvent.click(screen.getByRole("button", { name: "Avery account menu" }));
    expect(screen.getByText("Cedar Ridge branch")).toBeInTheDocument();
    expect(screen.getByText("Midwest")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Profile" })).toBeInTheDocument();
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
