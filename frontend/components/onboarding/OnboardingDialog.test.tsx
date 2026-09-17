import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import Dashboard from "@/pages/Dashboard";
import type {
  AgentJourneyTool,
  AgentOnboardingJourney,
  DashboardPageProps,
  OnboardingOfficeSelection,
  OnboardingProfileProps,
} from "@/types";

const pageProps = vi.hoisted(() => ({ current: {} as DashboardPageProps }));
const router = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  reload: vi.fn(),
  visit: vi.fn(),
  on: vi.fn(() => () => undefined),
}));

vi.mock("@inertiajs/react", async () => {
  const { useState } = await import("react");
  return {
    usePage: () => ({ props: pageProps.current, url: "/dashboard" }),
    Deferred: ({ children }: { children: ReactNode }) => children,
    Head: () => null,
    Link: ({ href, children }: { href: string; children: ReactNode }) => (
      <a href={href}>{children}</a>
    ),
    router,
    useRemember: <T,>(initialState: T) => useState<T>(initialState),
  };
});

// The profile form has its own tests. Here it only has to take focusable
// input and report unsaved edits the way the real flow does.
vi.mock("@/components/onboarding/profile/OnboardingProfileFlow", () => ({
  OnboardingProfileFlow: ({
    onDirtyChange,
  }: {
    onDirtyChange?: (dirty: boolean) => void;
  }) => (
    <form aria-label="Contact details">
      <label htmlFor="phone">Phone number</label>
      <input id="phone" onInput={() => onDirtyChange?.(true)} />
      <button type="submit">Save and continue</button>
    </form>
  ),
}));

const TITLE = "Finish setting up your oNEST profile";

function strictJourney(): AgentOnboardingJourney {
  return {
    schemaVersion: 1,
    profile: { state: "in_progress", label: "In progress", updatedAt: null },
    office: { state: "selected", label: "Selected", updatedAt: null },
    officeHandoff: {
      state: "pending",
      label: "Pending",
      updatedAt: null,
      recipient: null,
      message: "We are recording the handoff to your office administrator.",
      delivery: { state: "pending", label: "Pending", channels: [] },
    },
    contract: {
      state: "unavailable",
      label: "Unavailable",
      detail: "Contract status is not available right now.",
      actionHref: "/support/it",
      actionLabel: "Contact IT Support",
      updatedAt: null,
    },
    toolsSource: "available",
    tools: [],
    invitationInbox: {
      email: "agent@onest.realestate",
      followUpHours: 48,
      overdue: false,
      supportHref: "/support/it",
    },
    requiredSetupComplete: false,
    activationComplete: false,
    strictGateActive: true,
    currentStep: { code: "profile", label: "Profile" },
    nextAction: {
      code: "complete_profile",
      label: "Continue profile setup",
      href: "/onboarding",
      method: "get",
    },
    version: "1:now",
    updatedAt: "2026-08-19T09:00:00-04:00",
    blockers: [],
  };
}

function tool(overrides: Partial<AgentJourneyTool> = {}): AgentJourneyTool {
  return {
    key: "crm",
    label: "Brokerage CRM",
    description: "",
    provisioning: "onest",
    provisioningLabel: "Set up by oNEST",
    selfService: false,
    required: true,
    state: "invitation_sent",
    stateLabel: "Invitation sent",
    status: "pending",
    statusLabel: "Pending",
    invitationState: "sent",
    invitationLabel: "Invitation sent by your office",
    invitationSentAt: "2026-08-19T10:00:00-04:00",
    complete: false,
    applicable: true,
    updatedAt: null,
    helpUrl: "",
    requestPath: "",
    contact: "IT support",
    ...overrides,
  };
}

function releasedJourney(
  overrides: Partial<AgentOnboardingJourney> = {},
): AgentOnboardingJourney {
  return {
    ...strictJourney(),
    profile: { state: "complete", label: "Complete", updatedAt: null },
    office: { state: "confirmed", label: "Confirmed", updatedAt: null },
    officeHandoff: {
      ...strictJourney().officeHandoff,
      state: "notified",
      label: "Notified",
      recipient: { name: "Avery Admin" },
      message: "We notified Avery Admin. Their onboarding workspace is ready.",
    },
    contract: {
      state: "generated",
      label: "Being prepared",
      detail: "Your contract has been drafted.",
      actionHref: null,
      actionLabel: null,
      updatedAt: null,
    },
    tools: [tool()],
    requiredSetupComplete: true,
    strictGateActive: false,
    currentStep: { code: "activation", label: "Activation" },
    nextAction: {
      code: "wait_for_activation",
      label: "Your activation is still in progress",
      href: null,
      method: null,
    },
    ...overrides,
  };
}

const OFFICE: OnboardingOfficeSelection = {
  office: {
    id: 7,
    name: "Charlottesville",
    hierarchy: "oNEST · Mid-Atlantic · Charlottesville",
    region: "Mid-Atlantic",
    streetAddress: "100 Main Street",
    city: "Charlottesville",
    state: "VA",
    zipCode: "22902",
    mainPhone: "(434) 555-0100",
    publicEmail: "cville@onest.realestate",
    officeHours: [],
  },
  administrator: {
    id: 3,
    name: "Avery Admin",
    phone: "",
    email: "avery.admin@onest.realestate",
    isPrimary: true,
    resolutionLevel: "office",
    resolutionLabel: "Office Branch Admin",
  },
  support: { available: true, message: "" },
};

function setPage(overrides: Partial<DashboardPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "bob@onest.realestate",
      name: "Bob Lee",
      headshotUrl: null,
      permissions: [],
      roles: ["realtor"],
      roleLabel: "Realtor",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "request-1",
    features: {},
    primaryOffice: null,
    shell: {
      authorizationVersion: "access-v1",
      capabilitySchemaVersion: "p0-permissions-v1",
      help: { url: null },
      session: { authenticated: true },
    },
    notifications: null,
    greeting: {
      salutation: "Good morning",
      name: "Bob",
      dateLabel: "Wednesday, August 19",
      dateIso: "2026-08-19",
      timezone: "America/New_York",
    },
    ...overrides,
  };
}

function setStrictPage() {
  setPage({
    onboardingJourney: strictJourney(),
    // Opaque to this test: the mocked flow does not read it.
    onboardingProfile: {} as OnboardingProfileProps,
  });
}

/** Radix registers its outside-pointer listener on the next tick. */
async function nextTick() {
  await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
}

beforeEach(() => {
  for (const mock of Object.values(router)) {
    mock.mockClear();
  }
  window.localStorage.clear();
});

describe("Onboarding dialog under the strict gate", () => {
  beforeEach(setStrictPage);

  it("opens over the dashboard shell, named and described, starting at its title", () => {
    render(<Dashboard />);

    const dialog = screen.getByRole("dialog", { name: TITLE });
    expect(dialog).toHaveAccessibleDescription(
      "We use these details for your office, contracts, and internal directory.",
    );
    expect(within(dialog).getByRole("heading", { name: TITLE })).toHaveFocus();
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Good morning, Bob",
        hidden: true,
      }),
    ).toBeInTheDocument();
    expect(document.querySelector("[data-dashboard-slot]")).toBeNull();
  });

  it("offers no way to dismiss it: no close button, Escape, or outside click", async () => {
    const user = userEvent.setup();
    render(<Dashboard />);
    const dialog = screen.getByRole("dialog", { name: TITLE });
    expect(
      within(dialog).queryByRole("button", { name: "Close dialog" }),
    ).not.toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: TITLE })).toBeVisible();

    await nextTick();
    fireEvent.pointerDown(document.body);
    expect(screen.getByRole("dialog", { name: TITLE })).toBeVisible();
  });

  it("keeps keyboard focus inside the dialog", async () => {
    const user = userEvent.setup();
    render(<Dashboard />);
    const dialog = screen.getByRole("dialog", { name: TITLE });
    for (let step = 0; step < 6; step += 1) {
      await user.tab();
      expect(dialog).toContainElement(document.activeElement as HTMLElement);
    }
    for (let step = 0; step < 6; step += 1) {
      await user.tab({ shift: true });
      expect(dialog).toContainElement(document.activeElement as HTMLElement);
    }
  });

  it("shows three stages as words and icons, marking only the current one", () => {
    render(<Dashboard />);
    const stages = within(screen.getByRole("dialog", { name: TITLE })).getAllByRole(
      "listitem",
    );
    expect(stages.map((stage) => stage.textContent)).toEqual([
      "Your profileIn progress",
      "Your officeSelected",
      "Next stepsAfter setup",
    ]);
    expect(stages[0]).toHaveAttribute("aria-current", "step");
    expect(stages[1]).not.toHaveAttribute("aria-current");
    for (const stage of stages) {
      expect(stage.querySelector("svg")).not.toBeNull();
    }
  });

  it("signs out through Inertia once, with the action reachable by keyboard", async () => {
    const user = userEvent.setup();
    render(<Dashboard />);
    const signOut = screen.getByRole("button", { name: "Sign out" });

    signOut.focus();
    await user.keyboard("{Enter}");
    expect(router.post).toHaveBeenCalledTimes(1);
    expect(router.post).toHaveBeenCalledWith("/logout", {}, expect.any(Object));
    expect(screen.getByRole("button", { name: "Signing out…" })).toBeDisabled();
  });

  it("warns before signing out over unsaved edits", async () => {
    const user = userEvent.setup();
    render(<Dashboard />);
    await user.type(screen.getByLabelText("Phone number"), "202");

    await user.click(screen.getByRole("button", { name: "Sign out" }));
    const guard = screen.getByRole("dialog", { name: "Sign out without saving?" });
    expect(router.post).not.toHaveBeenCalled();

    await user.click(within(guard).getByRole("button", { name: "Keep editing" }));
    expect(
      screen.queryByRole("dialog", { name: "Sign out without saving?" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Phone number")).toHaveValue("202");

    await user.click(screen.getByRole("button", { name: "Sign out" }));
    await user.click(
      within(
        screen.getByRole("dialog", { name: "Sign out without saving?" }),
      ).getByRole("button", { name: "Sign out" }),
    );
    expect(router.post).toHaveBeenCalledTimes(1);
  });

  it("becomes the activation center when the server releases the gate, and says so", () => {
    const { rerender } = render(<Dashboard />);
    setPage({
      onboardingJourney: releasedJourney(),
      onboardingActivation: { autoOpen: true, office: OFFICE, guides: {} },
    });
    rerender(<Dashboard />);

    const dialog = screen.getByRole("dialog", { name: "Next steps" });
    expect(within(dialog).getByRole("status")).toHaveTextContent(
      "Your profile and office are confirmed. Next steps are now available.",
    );
    expect(within(dialog).getByRole("heading", { name: "Next steps" })).toHaveFocus();
    expect(
      within(dialog).getByRole("button", { name: "Close dialog" }),
    ).toBeInTheDocument();
  });

  it("has no detectable accessibility violations", async () => {
    render(<Dashboard />);
    expect(await axe(document.body)).toHaveNoViolations();
  });
});

describe("Activation center after release", () => {
  it("opens when the server asks, closes with Escape, and the status entry reopens it", async () => {
    const user = userEvent.setup();
    setPage({
      onboardingJourney: releasedJourney(),
      onboardingActivation: { autoOpen: true, office: OFFICE, guides: {} },
    });
    render(<Dashboard />);

    const dialog = screen.getByRole("dialog", { name: "Next steps" });
    expect(dialog).toHaveAccessibleDescription(
      "Your office administrator is handling the next steps.",
    );
    expect(within(dialog).getByText("Charlottesville")).toBeVisible();
    expect(
      within(dialog).getByRole("link", { name: "Email Avery Admin" }),
    ).toBeVisible();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const entry = screen.getByRole("button", { name: "View setup" });
    expect(entry).toHaveFocus();

    await user.click(entry);
    await user.click(screen.getByRole("button", { name: "Continue to dashboard" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(entry).toHaveFocus();
  });

  it("stays closed when the server did not ask, leaving the quiet status entry", () => {
    setPage({
      onboardingJourney: releasedJourney(),
      onboardingActivation: { autoOpen: false, office: OFFICE, guides: {} },
    });
    render(<Dashboard />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Setup in progress" })).toBeVisible();
    expect(screen.getByText(/We notified Avery Admin/)).toBeVisible();
  });

  it("lists only what the server recorded, with a state word beside each step", () => {
    setPage({
      onboardingJourney: releasedJourney({
        tools: [
          tool(),
          tool({
            key: "transactions",
            label: "Transaction platform",
            invitationState: "pending",
            invitationLabel: "Not sent yet",
            statusLabel: "Waiting for your office",
          }),
        ],
      }),
      onboardingActivation: { autoOpen: true, office: null, guides: {} },
    });
    render(<Dashboard />);

    const steps = within(screen.getByRole("dialog", { name: "Next steps" }))
      .getAllByRole("listitem")
      .slice(3)
      .map((item) => item.textContent);
    expect(steps).toEqual([
      "Office handoffWe notified Avery Admin. Their onboarding workspace is ready.Done",
      "Agent contractBeing preparedYour contract has been drafted.Waiting",
      "Brokerage CRMInvitation sent by your officeWaiting",
      "Transaction platformWaiting for your officeWaiting",
    ]);
  });

  it("routes a failed handoff to IT Support without claiming delivery", () => {
    const failed = releasedJourney();
    failed.officeHandoff = {
      ...failed.officeHandoff,
      state: "notification_failed",
      recipient: null,
      message: "We could not notify an office administrator.",
    };
    setPage({
      onboardingJourney: failed,
      onboardingActivation: { autoOpen: true, office: null, guides: {} },
    });
    render(<Dashboard />);

    const dialog = screen.getByRole("dialog", { name: "Next steps" });
    expect(dialog).toHaveAccessibleDescription(
      "We could not notify an office administrator.",
    );
    expect(within(dialog).queryByText(/is handling the next steps/)).toBeNull();
    expect(
      within(dialog).getByRole("link", { name: "Contact IT Support" }),
    ).toBeVisible();
  });

  it("has no detectable accessibility violations", async () => {
    setPage({
      onboardingJourney: releasedJourney(),
      onboardingActivation: { autoOpen: true, office: OFFICE, guides: {} },
    });
    render(<Dashboard />);
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
