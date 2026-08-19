import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { HubLayout } from "@/components/HubLayout";
import { HUB_NAV_GROUPS } from "@/lib/hub-nav";
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
  const base: HubFeatures = {};
  for (const group of HUB_NAV_GROUPS) {
    for (const item of group.items) {
      if (item.feature) {
        base[item.feature] = false;
      }
    }
  }
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
 * Visible item labels. The first span in a nav link is the title; the rest of
 * the link is the decorative marker and the screen-reader sentence.
 */
function navTitles() {
  return within(nav())
    .getAllByRole("link")
    .map((link) => link.querySelector("span")?.textContent ?? "");
}

function approvedTitles() {
  return HUB_NAV_GROUPS.flatMap((group) => group.items).map((item) => item.title);
}

beforeEach(() => {
  routerPost.mockClear();
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

  it("explains an unbuilt destination to assistive tech, not just visually", () => {
    render(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    const link = within(nav()).getByRole("link", {
      name: /My contract/,
    });
    expect(link).toHaveAccessibleDescription("My contract is not available yet");
  });

  it("drops the marker once the backend enables the module", () => {
    setPage({ features: features({ "my-contract": true }) });
    render(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    const link = within(nav()).getByRole("link", { name: /My contract/ });
    expect(link).not.toHaveAccessibleDescription();
  });

  it("keeps office destinations present and explained when there is no office", () => {
    setPage({
      primaryOffice: null,
      features: features({
        "office-info": true,
        "office-resources": true,
        "office-inventory": true,
      }),
    });
    render(
      <HubLayout>
        <p>content</p>
      </HubLayout>,
    );
    expect(screen.getByText("My office")).toBeInTheDocument();
    const link = within(nav()).getByRole("link", { name: /Office info/ });
    expect(link).toHaveAccessibleDescription(
      "Office info needs an office on your profile",
    );
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
