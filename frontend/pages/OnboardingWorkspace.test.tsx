import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import OnboardingWorkspace from "@/pages/OnboardingWorkspace";
import type { OnboardingWorkspacePageProps } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as OnboardingWorkspacePageProps,
}));

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({
    props: pageProps.current,
    url: "/operations/new-agents/9",
  }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: vi.fn(), post: vi.fn() },
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
      permissions: ["web.view_new_agents", "web.manage_new_agent_onboarding"],
      roles: ["Admins"],
      roleLabel: "Admin",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "00000000-0000-4000-8000-000000000001",
    features: {},
    primaryOffice: null,
    shell: {
      authorizationVersion: "v1",
      help: { url: null },
      session: { authenticated: true },
    },
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
          status: "pending",
          statusLabel: "Pending",
          tone: "warning",
          updatedAt: null,
          updatedBy: null,
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
      editable: true,
      ...overrides,
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

beforeEach(() => setPage());

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

  it("keeps operational task resolution explicit and versioned", () => {
    render(<OnboardingWorkspace />);
    const button = screen.getByRole("button", { name: /resolve/i });
    const form = button.closest("form");
    expect(form).toHaveAttribute("action", "/operations/new-agents/9/tasks");
    expect(form?.querySelector('input[name="expected_version"]')).toHaveAttribute(
      "value",
      "2026-08-19T12:00:00+00:00",
    );
  });

  it("makes every operational control read-only without manage permission", () => {
    setPage({ editable: false });
    render(<OnboardingWorkspace />);
    expect(screen.getByRole("button", { name: /save owner/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
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
