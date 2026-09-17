import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ComplianceAdministration from "@/pages/ComplianceAdministration";
import type { ComplianceAdministrationPageProps, ComplianceAdminRow } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as ComplianceAdministrationPageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/compliance" }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet },
}));

function row(overrides: Partial<ComplianceAdminRow> = {}): ComplianceAdminRow {
  return {
    id: 3,
    title: "Fair housing",
    summary: "Required annual review.",
    status: {
      code: "published",
      label: "Published",
      tone: "success",
      known: true,
    },
    statusCode: "published",
    category: { code: "agency", label: "Agency", tone: "neutral", known: true },
    versionNumber: 1,
    versionLabel: "v1",
    ownerOffice: { id: 4, name: "Fairfax VA" },
    scopeLevel: "office",
    audience: [
      {
        kind: "company",
        label: "Everyone at oNEST",
        code: "",
        officeId: null,
        userId: null,
      },
    ],
    jurisdictionStateCodes: ["VA"],
    isMandatory: true,
    effectiveAt: null,
    expiresAt: null,
    publishedAt: "2026-09-11T12:00:00Z",
    updatedAt: "2026-09-11T12:00:00Z",
    updatedBy: "Ada Admin",
    createdBy: "Ada Admin",
    version: "2026-09-11T12:00:00+00:00",
    ...overrides,
  };
}

function setPage(overrides: Partial<ComplianceAdministrationPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: ["web.manage_policies"],
      roles: ["broker_admin"],
      roleLabel: "Broker Admin",
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
    policies: {
      items: [row()],
      pagination: {
        page: 1,
        pageSize: 20,
        totalItems: 1,
        totalPages: 1,
        hasNext: false,
        hasPrevious: false,
      },
      filters: { q: "", status: "", category: "", office: "" },
      sort: { key: "updatedAt", direction: "desc" },
    },
    summary: { draft: 0, inReview: 1, published: 3 },
    filterOptions: {
      categories: [{ value: "agency", label: "Agency" }],
      statuses: [{ value: "published", label: "Published" }],
      offices: [{ value: 4, label: "Fairfax VA" }],
    },
    createOptions: {
      offices: [{ value: 4, label: "Fairfax VA" }],
      categories: [{ value: "agency", label: "Agency" }],
      audience: {
        canTargetCompany: true,
        regions: [],
        offices: [{ value: 4, label: "Fairfax VA" }],
        roles: [{ value: "realtor", label: "Realtor" }],
      },
    },
    capabilities: {
      canAuthor: true,
      canApprove: true,
      canPublish: true,
      canViewAcks: true,
      canWaive: true,
    },
    errors: { fields: {}, form: [] },
    ...overrides,
  } as ComplianceAdministrationPageProps;
}

describe("ComplianceAdministration", () => {
  beforeEach(() => {
    setPage();
    routerGet.mockClear();
  });

  it("renders the queue metrics and a policy link", () => {
    render(<ComplianceAdministration />);
    expect(screen.getByRole("heading", { name: "Compliance" })).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("In review")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fair housing" })).toHaveAttribute(
      "href",
      "/operations/compliance/3/edit",
    );
    expect(screen.getByRole("link", { name: "Acknowledgements" })).toBeInTheDocument();
  });

  it("visits with a status filter", async () => {
    const user = userEvent.setup();
    render(<ComplianceAdministration />);
    await user.click(screen.getByRole("button", { name: /filters/i }));
    await user.click(screen.getByRole("combobox", { name: "Status" }));
    await user.click(screen.getByRole("option", { name: "Published" }));
    expect(routerGet).toHaveBeenCalled();
  });
});
