import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ComplianceAckReport from "@/pages/ComplianceAckReport";
import type { ComplianceAckReportPageProps } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as ComplianceAckReportPageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({
    props: pageProps.current,
    url: "/operations/compliance/acknowledgements",
  }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet, post: routerPost },
}));

function setPage(overrides: Partial<ComplianceAckReportPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: [
        "web.view_policy_acknowledgements",
        "web.waive_policy_acknowledgements",
      ],
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
    flash: {},
    report: {
      items: [
        {
          userId: 4,
          userName: "Alex Agent",
          email: "alex@example.com",
          officeName: "Fairfax VA",
          policyId: 12,
          policyTitle: "Handbook",
          status: "overdue",
          dueAt: "2026-01-15T00:00:00Z",
          acknowledgedAt: null,
        },
      ],
      totalItems: 1,
    },
    filterOptions: {
      policies: [{ value: "12", label: "Handbook" }],
      offices: [{ value: "fairfax-va", label: "Fairfax VA" }],
      regions: [],
      roles: [{ value: "realtor", label: "Realtor" }],
      statuses: [
        { value: "pending", label: "Pending" },
        { value: "overdue", label: "Overdue" },
      ],
    },
    filters: {
      policy: "",
      office: "",
      region: "",
      role: "",
      dueFrom: "",
      dueTo: "",
      status: "",
      q: "",
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
  } as ComplianceAckReportPageProps;
}

describe("ComplianceAckReport", () => {
  beforeEach(() => {
    setPage();
    routerGet.mockClear();
    routerPost.mockClear();
  });

  it("renders acknowledgement rows and a waive action", async () => {
    const user = userEvent.setup();
    render(<ComplianceAckReport />);
    expect(screen.getByText("Alex Agent")).toBeInTheDocument();
    expect(screen.getByText("Handbook")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Waive" }));
    expect(
      screen.getByRole("heading", { name: "Waive acknowledgement" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm waiver" })).toBeInTheDocument();
  });

  it("visits with a status filter", async () => {
    const user = userEvent.setup();
    render(<ComplianceAckReport />);
    await user.click(screen.getByRole("combobox", { name: "Status" }));
    await user.click(screen.getByRole("option", { name: "Overdue" }));
    expect(routerGet).toHaveBeenCalled();
  });
});
