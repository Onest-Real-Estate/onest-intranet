import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import UserAdministration from "@/pages/UserAdministration";
import type { AdministrationPayload, UserAdministrationPageProps } from "@/types";

const pageProps = vi.hoisted(() => ({ current: {} as UserAdministrationPageProps }));

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({
    props: pageProps.current,
    url: "/operations/users/9/administration",
  }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: vi.fn(), post: vi.fn() },
}));

const administration: AdministrationPayload = {
  subject: {
    id: 9,
    email: "bob@onest.realestate",
    displayName: "Bob Lee",
    legalName: "Bob Lee",
    preferredDisplayName: "Bobby",
    headshotUrl: null,
    isActive: true,
    isSelf: false,
    office: {
      id: 7,
      name: "Fairfax VA",
      pathLabel: "Mid-Atlantic / Virginia / Fairfax VA",
      regionName: "Mid-Atlantic",
      isActive: true,
      isAssignable: true,
    },
    profileCompleted: true,
  },
  values: {
    officeId: "7",
    agentStatus: "active",
    startDate: "2024-02-01",
    agentIdentifier: "ON-4412",
    licenseVerificationState: "unverified",
    licenseVerificationNote: "",
    internalNotes: "",
  },
  version: "2026-08-01T10:00:00+00:00",
  fields: [
    {
      key: "office",
      prop: "officeId",
      label: "Office",
      description: "Determines what this person can see across the hub.",
      source: "Broker administration",
      highImpact: true,
      private: false,
    },
    {
      key: "agent_status",
      prop: "agentStatus",
      label: "Agent status",
      description: "Where this person stands with the brokerage.",
      source: "Broker administration",
      highImpact: true,
      private: false,
    },
  ],
  license: {
    number: "VA-9911",
    state: "VA",
    expiresOn: "2030-06-30",
    verification: {
      state: "unverified",
      label: "Not verified",
      tone: "neutral",
      verifiedAt: null,
      verifiedBy: null,
      note: "",
    },
  },
  contractStatus: {
    status: null,
    label: "Not connected",
    tone: "neutral",
    source: "contract",
    available: false,
    reason: "Agent contracts are not connected to the hub yet.",
  },
  accountState: {
    isActive: true,
    label: "Active",
    tone: "success",
    lastLoginAt: "2026-08-19T08:15:00+00:00",
    joinedAt: "2024-02-01T09:00:00+00:00",
    canManage: true,
    reason: "",
    sessionPolicy:
      "Disabling ends every signed-in session immediately and blocks the next request.",
  },
  provenance: {
    lastChangedAt: "2026-08-01T10:00:00+00:00",
    lastChangedBy: "Ada Admin",
  },
  history: [
    {
      id: "evt-1",
      action: "user.administration.updated",
      label: "Administrative record updated",
      occurredAt: "2026-08-01T10:00:00+00:00",
      actor: "ada@onest.realestate",
      outcome: "success",
      fields: ["agent_status"],
      reason: "",
    },
  ],
  assignments: [
    {
      id: 21,
      role: "realtor",
      roleLabel: "Realtor",
      roleDescription: "Licensed agent. Default role for new signups.",
      scopeType: "office",
      scopeLabel: "Fairfax VA",
      status: "active",
      startsAt: null,
      endsAt: null,
      assignedBy: "Ada Admin",
      businessReason: "Primary office",
      canRevoke: true,
    },
    {
      id: 22,
      role: "branch_manager",
      roleLabel: "Branch Manager",
      roleDescription: "Owns a branch or regional office.",
      scopeType: "office",
      scopeLabel: "Charlottesville VA",
      status: "active",
      startsAt: null,
      endsAt: null,
      assignedBy: "Ada Admin",
      businessReason: "Cover",
      canRevoke: false,
    },
  ],
  effectiveAccess: {
    roles: ["Realtor"],
    scopeLabel: "Fairfax VA",
    isSuperuser: false,
    liveAssignments: 2,
  },
  options: {
    agentStatuses: [
      { value: "active", label: "Active", tone: "success" },
      { value: "departed", label: "Departed", tone: "neutral" },
    ],
    licenseVerificationStates: [
      { value: "unverified", label: "Not verified", tone: "neutral" },
      { value: "verified", label: "Verified", tone: "success" },
    ],
    offices: [
      {
        id: 7,
        name: "Fairfax VA",
        pathLabel: "Mid-Atlantic / Virginia / Fairfax VA",
        regionName: "Mid-Atlantic",
      },
      {
        id: 8,
        name: "Charlottesville VA",
        pathLabel: "Mid-Atlantic / Virginia / Charlottesville VA",
        regionName: "Mid-Atlantic",
      },
    ],
    roles: [
      {
        value: "branch_manager",
        label: "Branch Manager",
        description: "Owns a branch or regional office.",
        scopes: [{ value: "office", label: "Office" }],
      },
    ],
  },
  editable: { administration: true, roleAssignments: true },
  highImpactFields: ["agent_status", "office"],
};

function setPage(overrides: Partial<AdministrationPayload> = {}, extra = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: ["user.view_user_administration", "user.change_user_administration"],
      roles: ["System Admin"],
      roleLabel: "System Admin",
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
    administration: { ...administration, ...overrides },
    validation: { fields: {}, form: [] },
    statusOptions: administration.options.agentStatuses,
    verificationOptions: administration.options.licenseVerificationStates,
    ...extra,
  } as UserAdministrationPageProps;
}

beforeEach(() => setPage());

/** The record's own office control, not the grant form's scope control. */
function officeSelect(): HTMLElement {
  const control = screen
    .getAllByRole("combobox")
    .find((element) => element.id === "office");
  if (!control) {
    throw new Error("office select not rendered");
  }
  return control;
}

describe("UserAdministration", () => {
  it("renders the subject and what their access currently resolves to", () => {
    render(<UserAdministration />);
    expect(screen.getByRole("heading", { name: "Bob Lee" })).toBeInTheDocument();
    expect(
      screen.getByText(
        /bob@onest\.realestate · Mid-Atlantic \/ Virginia \/ Fairfax VA/,
      ),
    ).toBeInTheDocument();
    // Provenance: the record names who last touched it, not just when.
    expect(screen.getAllByText("Ada Admin").length).toBeGreaterThan(0);
  });

  it("shows contract status as derived, with no control to change it", () => {
    render(<UserAdministration />);
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    expect(screen.getByText(/Agent contracts are not connected/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/contract status/i)).toBeNull();
  });

  it("confirms a high-impact change before it is submitted", async () => {
    const user = userEvent.setup();
    render(<UserAdministration />);

    await user.click(officeSelect());
    await user.click(screen.getByRole("option", { name: /Charlottesville VA/ }));
    await user.click(
      screen.getByRole("button", { name: /save administrative record/i }),
    );

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Confirm the access change/)).toBeInTheDocument();
    expect(within(dialog).getAllByText(/Charlottesville VA/).length).toBeGreaterThan(0);
    expect(
      within(dialog).getByText(/Agent assignment in the old office is retired/),
    ).toBeInTheDocument();
  });

  it("saves without a confirmation step when nothing high-impact changed", async () => {
    const user = userEvent.setup();
    render(<UserAdministration />);
    await user.type(screen.getByLabelText(/verification note/i), "Checked DPOR");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders the whole record read-only for the administrator's own account", () => {
    setPage({
      subject: { ...administration.subject, isSelf: true },
      editable: { administration: false, roleAssignments: false },
    });
    render(<UserAdministration />);
    expect(screen.getByText(/This is your own record/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save administrative record/i }),
    ).toBeDisabled();
  });

  it("does not offer revoke for an assignment outside the actor's delegation", () => {
    render(<UserAdministration />);
    const rows = screen.getAllByRole("row");
    const branchRow = rows.find((row) => row.textContent?.includes("Branch Manager"));
    expect(branchRow).toBeDefined();
    expect(
      within(branchRow as HTMLElement).queryByRole("button", { name: /revoke/i }),
    ).toBeNull();
    expect(
      within(branchRow as HTMLElement).getByText(/Outside your delegation/),
    ).toBeInTheDocument();
  });

  it("reports server validation errors in an accessible summary", () => {
    setPage(
      {},
      {
        validation: {
          fields: { agent_identifier: ["Another user already has that agent ID."] },
          form: [],
        },
      },
    );
    render(<UserAdministration />);
    const summary = screen.getByRole("alert", {
      name: /check the highlighted fields/i,
    });
    expect(within(summary).getByText(/Agent ID/)).toBeInTheDocument();
    expect(screen.getByLabelText(/agent id/i)).toHaveAttribute("aria-invalid", "true");
  });

  it("surfaces a concurrent-edit conflict as a form-level message", () => {
    setPage(
      {},
      {
        validation: {
          fields: {},
          form: ["Somebody else changed this record while you were editing it."],
        },
      },
    );
    render(<UserAdministration />);
    expect(screen.getByText(/Somebody else changed this record/)).toBeInTheDocument();
  });

  it("omits operational notes and contract standing without their grants", () => {
    const { internalNotes, ...values } = administration.values;
    setPage({
      values,
      contractStatus: undefined,
      fields: administration.fields.filter((field) => !field.private),
    });
    render(<UserAdministration />);
    expect(screen.queryByLabelText(/^notes$/i)).toBeNull();
    expect(screen.queryByText("Operational notes")).toBeNull();
    expect(screen.queryByText(/Agent contracts are not connected/)).toBeNull();
  });

  it("confirms a disable, naming the session consequence and demanding a reason", async () => {
    const user = userEvent.setup();
    render(<UserAdministration />);
    await user.click(screen.getByRole("button", { name: /disable account/i }));

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/signed out of every device immediately/i),
    ).toBeInTheDocument();
    const confirm = within(dialog).getByRole("button", { name: /disable account/i });
    expect(confirm).toBeDisabled();

    await user.type(
      within(dialog).getByLabelText(/business reason/i),
      "Left the brokerage on 14 March.",
    );
    expect(confirm).toBeEnabled();
  });

  it("posts the account change to its own endpoint with the version token", async () => {
    const user = userEvent.setup();
    render(<UserAdministration />);
    await user.click(screen.getByRole("button", { name: /disable account/i }));
    const dialog = await screen.findByRole("dialog");
    const form = within(dialog)
      .getByRole("button", { name: /disable account/i })
      .closest("form");
    expect(form).toHaveAttribute("action", "/operations/users/9/account-state");
    expect(form?.querySelector('input[name="action"]')).toHaveValue("disable");
    expect(form?.querySelector('input[name="expected_version"]')).toHaveValue(
      administration.version,
    );
  });

  it("offers reactivation, not disabling, for a disabled account", () => {
    setPage({
      accountState: {
        ...administration.accountState,
        isActive: false,
        label: "Disabled",
        tone: "destructive",
      },
    });
    render(<UserAdministration />);
    expect(
      screen.getByRole("button", { name: /reactivate account/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /disable account/i })).toBeNull();
  });

  it("explains why account access is read-only rather than hiding the panel", () => {
    setPage({
      accountState: {
        ...administration.accountState,
        canManage: false,
        reason: "Nobody changes their own account access.",
      },
    });
    render(<UserAdministration />);
    expect(screen.queryByRole("button", { name: /disable account/i })).toBeNull();
    expect(
      screen.getByText("Nobody changes their own account access."),
    ).toBeInTheDocument();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<UserAdministration />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
