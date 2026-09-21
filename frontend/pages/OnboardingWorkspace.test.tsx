import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FormHTMLAttributes, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import OnboardingWorkspace from "@/pages/OnboardingWorkspace";
import type { OnboardingWorkspacePageProps } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as OnboardingWorkspacePageProps,
}));
const router = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({
    props: pageProps.current,
    url: "/operations/new-agents/9",
  }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  Form: ({ children, ...props }: FormHTMLAttributes<HTMLFormElement>) => (
    <form {...props}>{children}</form>
  ),
  router,
}));

function setPage(
  overrides: Partial<OnboardingWorkspacePageProps["onboarding"]> = {},
  validation: OnboardingWorkspacePageProps["validation"] = {
    fields: {},
    form: [],
  },
) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: [
        "web.view_new_agents",
        "web.manage_new_agent_onboarding",
        "contract.manage_agent_contracts",
      ],
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
    onboarding: {
      user: {
        id: 9,
        name: "Bob Lee",
        email: "bob@onest.realestate",
        office: "Fairfax VA",
        region: "Mid-Atlantic",
        startDate: "2026-08-25",
        isActive: true,
      },
      owner: { id: 1, name: "Ada Admin" },
      overallStatus: "blocked",
      overall: { value: "blocked", label: "Blocked", tone: "destructive" },
      blockers: [
        { key: "contract_generated", label: "Contract source is not connected." },
      ],
      progress: { complete: 2, total: 10 },
      contractStatus: "unavailable",
      contract: {
        value: "unavailable",
        label: "Source unavailable",
        tone: "neutral",
      },
      trainingStatus: "unavailable",
      training: {
        value: "unavailable",
        label: "Source unavailable",
        tone: "neutral",
      },
      openTaskCount: 1,
      version: "2026-08-19T12:00:00+00:00",
      journeyVersion: "0:7:2026-08-19T12:00:00+00:00",
      lastChangedAt: "2026-08-19T12:00:00+00:00",
      lastChangedBy: "Ada Admin",
      milestones: [
        {
          key: "profile",
          label: "Profile complete",
          status: "complete",
          statusLabel: "Complete",
          tone: "success",
          source: "profile",
          detail: "Required profile details are complete.",
          updatedAt: "2026-08-18T12:00:00+00:00",
          correction: {
            label: "Open correction workflow",
            href: "/operations/users/9/administration",
          },
        },
        {
          key: "contract_generated",
          label: "Contract generated",
          status: "unavailable",
          statusLabel: "Source unavailable",
          tone: "neutral",
          source: "contract",
          detail: "The agent-contract source is not connected to the hub yet.",
          updatedAt: null,
          correction: null,
        },
      ],
      tools: [
        {
          key: "lofty",
          label: "Lofty",
          state: "not_started",
          stateLabel: "Not started",
          status: "pending",
          statusLabel: "Pending",
          tone: "warning",
          required: true,
          invitationState: "pending",
          invitationLabel: "Waiting on your office",
          invitationSentAt: null,
          updatedAt: null,
          updatedBy: null,
          description: "CRM and lead routing",
          provisioning: "office_invite",
          provisioningLabel: "Office invitation",
          selfService: false,
          group: "waiting",
          delivery: {
            state: "not_recorded",
            label: "Agent notice not recorded",
            retryable: false,
            channels: [],
          },
          actions: [
            {
              code: "mark_invitation_sent",
              label: "Mark invitation sent",
              tool: "lofty",
              requiresReason: false,
              enabled: true,
              unavailableReason: "",
            },
          ],
        },
      ],
      tasks: [
        {
          id: 21,
          title: "Confirm key pickup",
          dueOn: "2026-08-24",
          isBlocking: true,
          createdAt: "2026-08-19T12:00:00+00:00",
          createdBy: "Ada Admin",
        },
      ],
      eligibleNotices: [],
      contractAction: {
        code: "initiate_contract",
        label: "Initiate agent contract",
        method: "post",
        href: "/operations/new-agents/9/contract",
        enabled: true,
        unavailableReason: "",
        permission: "contract.manage_agent_contracts",
      },
      recommendedAction: {
        source: "tool",
        code: "mark_invitation_sent",
        label: "Mark invitation sent",
        description: "Continue Lofty setup.",
        tool: "lofty",
        enabled: true,
        unavailableReason: "",
      },
      editable: true,
      ...overrides,
    },
    profileSummary: {
      headshotUrl: "/operations/new-agents/9/headshot",
      sensitiveFieldsIncluded: true,
      fields: [
        { key: "legalName", label: "Legal name", value: "Bob Lee" },
        { key: "phoneNumber", label: "Phone", value: "(202) 555-0100" },
      ],
    },
    confirmedOffice: {
      office: {
        id: 7,
        name: "Fairfax VA",
        hierarchy: "Mid-Atlantic / Fairfax VA",
        region: "Mid-Atlantic",
        streetAddress: "1 Office Plaza",
        city: "Fairfax",
        state: "VA",
        zipCode: "22030",
        mainPhone: "(703) 555-0100",
        publicEmail: "fairfax@onest.realestate",
        officeHours: [],
      },
      administrator: {
        id: 1,
        name: "Ada Admin",
        phone: "(703) 555-0110",
        email: "ada@onest.realestate",
        isPrimary: true,
        resolutionLevel: "office",
        resolutionLabel: "Office Branch Admin",
      },
      support: { available: false, message: "" },
    },
    ownerOptions: [{ value: "1", label: "Ada Admin" }],
    toolStateOptions: [
      { value: "not_started", label: "Not started" },
      { value: "ready", label: "Ready" },
    ],
    activity: [],
    validation,
    privacy: {
      notesAllowed: false,
      taskPolicy:
        "Task titles are retained for two years after resolution. Do not include sensitive details.",
    },
  };
}

beforeEach(() => {
  setPage();
  router.get.mockReset();
  router.post.mockReset();
});

describe("OnboardingWorkspace", () => {
  it("renders derived milestones as read-only facts with permitted correction links", () => {
    render(<OnboardingWorkspace />);
    const path = screen.getByRole("heading", { name: "Activation path" }).parentElement
      ?.parentElement?.parentElement;
    expect(path).toBeTruthy();
    expect(within(path as HTMLElement).getByText("Profile complete")).toBeVisible();
    expect(
      within(path as HTMLElement).getByRole("link", {
        name: /open correction workflow/i,
      }),
    ).toHaveAttribute("href", "/operations/users/9/administration");
    expect(within(path as HTMLElement).queryByRole("checkbox")).toBeNull();
  });

  it("keeps operational task resolution explicit and versioned", async () => {
    const user = userEvent.setup();
    render(<OnboardingWorkspace />);
    const button = screen.getByRole("button", { name: /resolve/i });
    await user.click(button);
    expect(router.post).toHaveBeenCalledWith(
      "/operations/new-agents/9/tasks",
      {
        action: "resolve",
        task: 21,
        expected_version: "0:7:2026-08-19T12:00:00+00:00",
      },
      { preserveScroll: true },
    );
  });

  it("runs a catalog-provided tool action once with the journey version", async () => {
    const user = userEvent.setup();
    render(<OnboardingWorkspace />);
    const tool = screen.getByText("Lofty").closest("article");
    expect(tool).toBeTruthy();
    const action = within(tool as HTMLElement).getByRole("button", {
      name: "Mark invitation sent",
    });
    await user.dblClick(action);
    expect(router.post).toHaveBeenCalledTimes(1);
    expect(router.post).toHaveBeenCalledWith(
      "/operations/new-agents/9/tools",
      {
        expected_version: "0:7:2026-08-19T12:00:00+00:00",
        tool: "lofty",
        action: "mark_invitation_sent",
        reason: "",
      },
      expect.objectContaining({ preserveScroll: true }),
    );
    expect(screen.getByText("Waiting on your office")).toBeVisible();
  });

  it("requires a reason before a correction can be submitted", async () => {
    const user = userEvent.setup();
    const tool = pageProps.current.onboarding.tools[0];
    tool.state = "invitation_sent";
    tool.stateLabel = "Invitation sent";
    tool.actions = [
      {
        code: "revoke_invitation",
        label: "Correct invitation record",
        tool: "lofty",
        requiresReason: true,
        enabled: true,
        unavailableReason: "",
      },
    ];
    render(<OnboardingWorkspace />);
    const button = screen.getByRole("button", { name: "Correct invitation record" });
    expect(button).toBeDisabled();
    await user.type(
      screen.getByLabelText("Lofty correction reason"),
      "Sent to wrong account",
    );
    expect(button).toBeEnabled();
    await user.click(button);
    expect(router.post).toHaveBeenCalledWith(
      "/operations/new-agents/9/tools",
      expect.objectContaining({
        action: "revoke_invitation",
        reason: "Sent to wrong account",
      }),
      expect.any(Object),
    );
  });

  it("initiates a contract through the source-owned action", async () => {
    const user = userEvent.setup();
    render(<OnboardingWorkspace />);
    await user.click(screen.getByRole("button", { name: "Initiate agent contract" }));
    expect(router.post).toHaveBeenCalledWith(
      "/operations/new-agents/9/contract",
      { expected_version: "0:7:2026-08-19T12:00:00+00:00" },
      expect.objectContaining({ preserveScroll: true }),
    );
  });

  it("retries a failed office handoff from the recommended action", async () => {
    setPage({
      recommendedAction: {
        source: "handoff",
        code: "retry_office_handoff",
        label: "Retry office handoff",
        description: "The office handoff was not delivered.",
        method: "post",
        href: "/operations/new-agents/9/handoff",
        tool: null,
        enabled: true,
        unavailableReason: "",
      },
    });
    const user = userEvent.setup();
    render(<OnboardingWorkspace />);
    await user.dblClick(screen.getByRole("button", { name: "Retry office handoff" }));
    expect(router.post).toHaveBeenCalledTimes(1);
    expect(router.post).toHaveBeenCalledWith(
      "/operations/new-agents/9/handoff",
      { expected_version: "0:7:2026-08-19T12:00:00+00:00" },
      expect.any(Object),
    );
  });

  it("shows the submitted profile and confirmed office contact", () => {
    render(<OnboardingWorkspace />);
    expect(screen.getByRole("img", { name: "Bob Lee headshot" })).toHaveAttribute(
      "src",
      "/operations/new-agents/9/headshot",
    );
    expect(screen.getByText("1 Office Plaza, Fairfax VA 22030")).toBeVisible();
    expect(screen.getByRole("link", { name: "Call" })).toHaveAttribute(
      "href",
      "tel:(703) 555-0110",
    );
    expect(screen.getByRole("link", { name: "Email" })).toHaveAttribute(
      "href",
      "mailto:ada@onest.realestate",
    );
  });

  it("makes every operational control read-only without manage permission", () => {
    setPage({ editable: false });
    render(<OnboardingWorkspace />);
    expect(screen.getByRole("button", { name: /save owner/i })).toBeDisabled();
    expect(
      screen.getAllByRole("button", { name: /mark invitation sent/i })[0],
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /initiate agent contract/i }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: /resolve/i })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /add task/i })).toBeNull();
  });

  it("surfaces a stale edit as an accessible conflict", () => {
    setPage(
      {},
      {
        fields: {},
        form: ["Somebody else changed this onboarding record. Reload it."],
      },
    );
    render(<OnboardingWorkspace />);
    expect(
      screen.getByRole("alert", { name: /check the highlighted fields/i }),
    ).toHaveTextContent(/Somebody else changed/i);
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<OnboardingWorkspace />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
