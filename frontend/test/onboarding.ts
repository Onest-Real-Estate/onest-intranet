import type {
  AgentActivationGuide,
  AgentJourneyTool,
  AgentOnboardingJourney,
} from "@/types";

/**
 * Journey fixtures for onboarding tests.
 *
 * One place to add a field when the server contract grows, so a new key cannot
 * be typed into three suites three different ways — and so a test that cares
 * about one state says only that state in its overrides.
 */

export function agentTool(overrides: Partial<AgentJourneyTool> = {}): AgentJourneyTool {
  return {
    key: "lofty",
    label: "Lofty",
    description: "CRM, lead follow-up, campaigns, and your agent pipeline.",
    provisioning: "onest",
    provisioningLabel: "oNEST sets this up for you",
    selfService: false,
    required: true,
    state: "requested",
    stateLabel: "Requested",
    status: "pending",
    statusLabel: "Pending",
    invitationState: "pending",
    invitationLabel: "Waiting on your office",
    invitationSentAt: null,
    complete: false,
    applicable: true,
    updatedAt: null,
    helpUrl: "",
    requestPath: "",
    contact: "IT support",
    ...overrides,
  };
}

/** A tool whose office has recorded the invitation as sent. */
export function invitedTool(
  overrides: Partial<AgentJourneyTool> = {},
): AgentJourneyTool {
  return agentTool({
    state: "invitation_sent",
    stateLabel: "Invitation sent",
    invitationState: "sent",
    invitationLabel: "Invitation sent",
    invitationSentAt: "2026-08-19T10:00:00-04:00",
    ...overrides,
  });
}

export function activationGuide(
  overrides: Partial<AgentActivationGuide> = {},
): AgentActivationGuide {
  return {
    state: "available",
    contentId: 42,
    title: "Activate your Lofty account",
    summary: "Six minutes, start to finish.",
    estimatedMinutes: 6,
    href: "/training-learning/42",
    hasTranscript: true,
    inProgress: false,
    ...overrides,
  };
}

export function agentJourney(
  overrides: Partial<AgentOnboardingJourney> = {},
): AgentOnboardingJourney {
  return {
    schemaVersion: 1,
    profile: { state: "complete", label: "Complete", updatedAt: null },
    office: { state: "confirmed", label: "Confirmed", updatedAt: null },
    officeHandoff: {
      state: "pending",
      label: "Pending",
      updatedAt: null,
      recipient: null,
      message: "We are recording the handoff to your office administrator.",
      delivery: { state: "pending", label: "Pending", channels: [] },
    },
    contract: {
      state: "not_started",
      label: "Waiting for your office administrator",
      detail:
        "Your office administrator prepares your agent contract after your handoff.",
      actionHref: null,
      actionLabel: null,
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
    requiredSetupComplete: true,
    activationComplete: false,
    strictGateActive: false,
    currentStep: { code: "activation", label: "Activation" },
    nextAction: {
      code: "wait_for_office",
      label: "Your office administrator is handling the next steps",
      href: null,
      method: null,
    },
    version: "1:now",
    updatedAt: "2026-08-19T09:00:00-04:00",
    blockers: [],
    ...overrides,
  };
}
