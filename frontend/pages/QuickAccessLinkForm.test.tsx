import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import QuickAccessLinkForm from "@/pages/QuickAccessLinkForm";
import type { QuickAccessLinkFormPageProps, QuickAccessLinkRow } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as QuickAccessLinkFormPageProps,
}));
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/quick-access/new" }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { post: routerPost },
}));

const existing: QuickAccessLinkRow = {
  id: 7,
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
      { id: 4, name: "Fairfax VA", stableKey: "fairfax-va", includeDescendants: true },
    ],
  },
  canManage: true,
  updatedAt: "2026-08-20T12:00:00+00:00",
  version: "2026-08-20T12:00:00+00:00",
};

function setPage(overrides: Partial<QuickAccessLinkFormPageProps> = {}) {
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
    link: null,
    errors: { fields: {}, form: [] },
    posted: null,
    pendingConfirmation: [],
    iconOptions: [
      { value: "app-window", label: "Generic application" },
      { value: "contact", label: "CRM / contacts" },
    ],
    internalDestinations: [{ value: "hub:office-info", label: "Office info" }],
    destinationTypeOptions: [
      { value: "external_url", label: "External URL" },
      { value: "internal_route", label: "Internal route" },
    ],
    ssoOptions: [{ value: "none", label: "No single sign-on" }],
    healthOptions: [{ value: "unknown", label: "Not monitored" }],
    setupOptions: [{ value: "self_service", label: "Agent signs in directly" }],
    roleOptions: [
      { value: "realtor", label: "Realtor" },
      { value: "branch_manager", label: "Branch Manager" },
    ],
    officeOptions: [
      { value: 4, label: "Mid-Atlantic / Virginia / Fairfax VA" },
      { value: 5, label: "Mid-Atlantic / Virginia / Arlington VA" },
    ],
    capabilities: { companyWide: false, scopeLevel: "scoped" },
    ...overrides,
  } as QuickAccessLinkFormPageProps;
}

/**
 * The destination control, whichever shape it currently has.
 *
 * Queried by id rather than by label text: "Destination" is also the prefix of
 * "Destination type", and the required marker sits inside the label.
 */
function destinationField(): HTMLElement {
  const field = document.querySelector("#destination_value");
  if (!(field instanceof HTMLElement)) {
    throw new Error("destination control is missing");
  }
  return field;
}

beforeEach(() => {
  routerPost.mockClear();
  setPage();
});

describe("QuickAccessLinkForm", () => {
  it("confirms before publishing a brand new link", async () => {
    const user = userEvent.setup();
    render(<QuickAccessLinkForm />);
    await user.type(screen.getByLabelText(/^name/i), "New CRM");
    await user.type(screen.getByLabelText(/stable key/i), "new-crm");
    await user.type(destinationField(), "https://crm.example.com");
    await user.click(screen.getByLabelText(/Mid-Atlantic \/ Virginia \/ Fairfax VA/));
    await user.click(screen.getByRole("button", { name: /create link/i }));

    expect(routerPost).not.toHaveBeenCalled();
    expect(screen.getByText(/widens who can see the tool/i)).toBeVisible();

    await user.click(screen.getByRole("button", { name: /publish the change/i }));
    expect(routerPost).toHaveBeenCalledWith(
      "/operations/quick-access/submit",
      expect.objectContaining({
        stable_key: "new-crm",
        destination_value: "https://crm.example.com",
        acknowledge_exposure: "on",
      }),
      expect.anything(),
    );
  });

  it("confirms a destination change on an existing link", async () => {
    const user = userEvent.setup();
    setPage({ link: existing });
    render(<QuickAccessLinkForm />);
    const destination = destinationField();
    await user.clear(destination);
    await user.type(destination, "https://elsewhere.example.com");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(routerPost).not.toHaveBeenCalled();
    expect(
      screen.getByText(/Everyone who can see this link goes somewhere new/i),
    ).toBeVisible();
  });

  it("saves a narrowing change without a confirmation step", async () => {
    const user = userEvent.setup();
    setPage({ link: existing });
    render(<QuickAccessLinkForm />);
    // Adding a role narrows nothing away, and removing an office narrows: both
    // are safe directions, so neither should stop to ask.
    await user.click(screen.getByLabelText(/Mid-Atlantic \/ Virginia \/ Fairfax VA/));
    await user.click(screen.getByRole("button", { name: /save changes/i }));
    expect(routerPost).toHaveBeenCalledWith(
      "/operations/quick-access/7/submit",
      expect.objectContaining({ expected_version: existing.version }),
      expect.anything(),
    );
  });

  it("locks the stable key on an existing link", () => {
    setPage({ link: existing });
    render(<QuickAccessLinkForm />);
    expect(screen.getByLabelText(/stable key/i)).toBeDisabled();
  });

  it("disables the company-wide switch when the grant is not held", () => {
    render(<QuickAccessLinkForm />);
    expect(screen.getByLabelText(/publish company-wide/i)).toBeDisabled();
    expect(screen.getByText(/cannot publish brokerage-wide/i)).toBeVisible();
  });

  it("offers approved pages rather than a free-text path for internal links", async () => {
    const user = userEvent.setup();
    render(<QuickAccessLinkForm />);
    await user.click(screen.getByLabelText(/destination type/i));
    await user.click(screen.getByRole("option", { name: /internal route/i }));
    expect(destinationField()).toHaveAttribute("role", "combobox");
  });

  it("shows the server's field errors on the fields that failed", () => {
    setPage({
      errors: {
        fields: { destination_value: ["External links must start with https://."] },
        form: [],
      },
    });
    render(<QuickAccessLinkForm />);
    // The summary and the field both carry it; that is the intended pairing.
    expect(screen.getAllByText(/must start with https/i).length).toBeGreaterThan(0);
    expect(destinationField()).toHaveAttribute("aria-invalid", "true");
  });

  it("reopens the confirmation the server asked for", () => {
    setPage({
      pendingConfirmation: [
        {
          label: "Audience",
          from: "Fairfax VA",
          to: "Every office in the brokerage",
          impact: "The link becomes visible brokerage-wide.",
        },
      ],
    });
    render(<QuickAccessLinkForm />);
    expect(screen.getByText(/becomes visible brokerage-wide/i)).toBeVisible();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<QuickAccessLinkForm />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
