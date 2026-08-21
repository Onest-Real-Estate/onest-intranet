import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import QuickAccessAdministration from "@/pages/QuickAccessAdministration";
import type { QuickAccessAdministrationPageProps, QuickAccessLinkRow } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as QuickAccessAdministrationPageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/quick-access" }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet, post: routerPost },
}));

function link(overrides: Partial<QuickAccessLinkRow> = {}): QuickAccessLinkRow {
  return {
    id: 1,
    stableKey: "lofty",
    name: "Lofty",
    description: "",
    destinationType: "external_url",
    destinationValue: "https://www.lofty.com",
    href: "https://www.lofty.com",
    icon: "contact",
    sortOrder: 10,
    isActive: true,
    isArchived: false,
    status: { value: "live", label: "Live", tone: "success" },
    publishStartAt: null,
    publishEndAt: null,
    ssoCapability: "none",
    integrationHealth: "unknown",
    setupBehavior: "self_service",
    ownerScope: "scoped",
    ownerOffice: "Fairfax VA",
    audience: {
      companyWide: false,
      roles: [{ code: "realtor", label: "Realtor" }],
      offices: [
        {
          id: 4,
          name: "Fairfax VA",
          stableKey: "fairfax-va",
          includeDescendants: true,
        },
      ],
    },
    canManage: true,
    updatedAt: "2026-08-20T12:00:00+00:00",
    version: "2026-08-20T12:00:00+00:00",
    ...overrides,
  };
}

function setPage(overrides: Partial<QuickAccessAdministrationPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: ["web.manage_quick_access"],
      roles: ["branch_manager"],
      roleLabel: "Branch Manager",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "req-1",
    features: {},
    primaryOffice: null,
    shell: {
      authorizationVersion: "v1",
      capabilitySchemaVersion: "p0-permissions-v1",
      help: { url: null },
      session: { authenticated: true },
    },
    notifications: null,
    links: {
      items: [
        link(),
        link({ id: 2, stableKey: "skyslope", name: "SkySlope", sortOrder: 20 }),
      ],
      pagination: {
        page: 1,
        pageSize: 10,
        totalItems: 2,
        totalPages: 1,
        hasNext: false,
        hasPrevious: false,
      },
      filters: { q: "", status: "" },
      sort: { key: "sortOrder", direction: "asc" },
    },
    statusOptions: [
      { value: "live", label: "Live" },
      { value: "archived", label: "Archived" },
    ],
    roleOptions: [{ value: "realtor", label: "Realtor" }],
    officeOptions: [{ value: 4, label: "Mid-Atlantic / Virginia / Fairfax VA" }],
    preview: null,
    capabilities: { companyWide: false, scopeLevel: "scoped" },
    ...overrides,
  } as QuickAccessAdministrationPageProps;
}

beforeEach(() => {
  routerGet.mockClear();
  routerPost.mockClear();
  setPage();
});

describe("QuickAccessAdministration", () => {
  it("lists the links the server put in scope, in panel order", () => {
    render(<QuickAccessAdministration />);
    const rows = screen
      .getAllByRole("row")
      .filter(
        (row) =>
          row.textContent?.includes("lofty") || row.textContent?.includes("skyslope"),
      );
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Lofty");
    expect(rows[1].textContent).toContain("SkySlope");
  });

  it("summarizes the audience instead of showing a raw list", () => {
    render(<QuickAccessAdministration />);
    expect(screen.getAllByText(/Fairfax VA · Realtor/)[0]).toBeVisible();
  });

  it("posts the whole visible sequence when a link is moved", async () => {
    const user = userEvent.setup();
    render(<QuickAccessAdministration />);
    await user.click(screen.getByRole("button", { name: /move skyslope up/i }));
    expect(routerPost).toHaveBeenCalledWith(
      "/operations/quick-access/reorder",
      { order: "2,1" },
      expect.anything(),
    );
  });

  it("offers no controls for a link the server says it cannot manage", () => {
    setPage({
      links: {
        ...pageProps.current.links,
        items: [link({ canManage: false, ownerScope: "company" })],
      },
    });
    render(<QuickAccessAdministration />);
    expect(screen.queryByRole("button", { name: /deactivate/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /archive/i })).toBeNull();
  });

  it("archives rather than deletes", async () => {
    const user = userEvent.setup();
    render(<QuickAccessAdministration />);
    expect(screen.queryByRole("button", { name: /^delete$/i })).toBeNull();
    await user.click(screen.getAllByRole("button", { name: /archive/i })[0]);
    expect(routerPost).toHaveBeenCalledWith(
      "/operations/quick-access/1/state",
      { action: "archive" },
      expect.anything(),
    );
  });

  it("sends the search to the server rather than filtering in the browser", async () => {
    const user = userEvent.setup();
    render(<QuickAccessAdministration />);
    await user.type(screen.getByLabelText(/search links/i), "lofty{Enter}");
    expect(routerGet).toHaveBeenCalledWith(
      "/operations/quick-access",
      expect.objectContaining({ q: "lofty" }),
      expect.anything(),
    );
  });

  it("explains why each link is hidden in a preview", () => {
    setPage({
      preview: {
        roleCode: "realtor",
        officeId: 4,
        officeName: "Fairfax VA",
        outOfScope: false,
        links: [
          { id: 1, name: "Lofty", stableKey: "lofty", visible: true, reasons: [] },
          {
            id: 2,
            name: "SkySlope",
            stableKey: "skyslope",
            visible: false,
            reasons: [
              "Deactivated.",
              "This office is not in the link's office audience.",
            ],
          },
        ],
      },
    });
    render(<QuickAccessAdministration />);
    const hidden = screen
      .getAllByRole("listitem")
      .find((item) => item.textContent?.includes("SkySlope"));
    expect(hidden).toBeDefined();
    expect(within(hidden as HTMLElement).getByText(/Deactivated/)).toBeVisible();
    expect(
      within(hidden as HTMLElement).getByText(/not in the link's office audience/),
    ).toBeVisible();
  });

  it("says plainly when the previewed office is out of scope", () => {
    setPage({
      preview: {
        roleCode: "realtor",
        officeId: null,
        officeName: null,
        outOfScope: true,
        links: [],
      },
    });
    render(<QuickAccessAdministration />);
    expect(screen.getByText(/outside your scope/i)).toBeVisible();
  });

  it("renders the permission-denied page for a reader without the grant", () => {
    setPage({
      user: pageProps.current.user
        ? { ...pageProps.current.user, permissions: [] }
        : null,
    });
    render(<QuickAccessAdministration />);
    expect(screen.queryByRole("button", { name: /move/i })).toBeNull();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<QuickAccessAdministration />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
